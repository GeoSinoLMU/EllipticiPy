# Copyright (C) 2022 Stuart Russell
"""
This file contains the functions to support the calculation of ellipticity
corrections. All functions in this file are called by the main functions
in the main file.
"""

import numpy as np
from scipy.integrate import cumtrapz

from obspy.taup import TauPyModel
from obspy.taup.tau import TauModel

# Constants
EARTH_LOD = 86164.0905  # s, length of day of Earth
G = 6.67408e-11  # m^3 kg^-1 s^-2, universal gravitational constant


def model_epsilon(model, lod=EARTH_LOD):
    """
    Calculates a profile of ellipticity of figure through a planetary model.

    :param model: The tau model object
    :type model: :class:`obspy.taup.tau_model.TauModel`
    :param lod: length of day in seconds. Defaults to Earth value
    :type lod: float
    :returns: Adds arrays of epsilon (ellipticity of figure)at top and
        bottom of each velocity layer as attributes
        model.s_mod.v_mod.top_epsilon and model.s_mod.v_mod.bot_epsilon
    """

    # Angular velocity of planet
    omega = 2 * np.pi / lod  # s^-1

    # Radius of planet in m
    a = model.radius_of_planet * 1e3

    # Depth and density information of velocity layers
    v_mod = model.s_mod.v_mod  # velocity_model
    top_depth = v_mod.layers["top_depth"][::-1] * 1e3  # in m
    top_density = v_mod.layers["top_density"][::-1] * 1e3  # in kg m^-3
    bot_density = v_mod.layers["bot_density"][::-1] * 1e3  # in kg m^-3
    top_radius = a - top_depth

    # Mass within each spherical shell by trapezoidal rule
    top_volume = (4.0 / 3.0) * np.pi * top_radius**3
    volume = np.zeros(len(top_depth) + 1)
    volume[1:] = top_volume
    d_volume = volume[1:] - volume[:-1]
    d_mass = 0.5 * (bot_density + top_density) * d_volume
    mass = np.cumsum(d_mass)

    total_mass = mass[-1]

    # Moment of inertia of each spherical shell by trapezoidal rule
    j_top = (8.0 / 15.0) * np.pi * top_radius**5
    j = np.zeros(len(top_depth) + 1)
    j[1:] = j_top
    d_j = j[1:] - j[:-1]
    d_inertia = 0.5 * (bot_density + top_density) * d_j

    moment_of_inertia = np.cumsum(d_inertia)

    # Calculate y (moment of inertia factor) for surfaces within the body
    y = moment_of_inertia / (mass * top_radius**2)

    # Calculate Radau's parameter
    radau = 6.25 * (1 - 3 * y / 2) ** 2 - 1

    # Calculate h, ratio of centrifugal force and gravity for a particle
    # on the equator at the surface
    ha = (a**3 * omega**2) / (G * total_mass)

    # epsilon at surface
    epsilona = (5 * ha) / (2 * radau[-1] + 4)

    # Solve the differential equation
    epsilon = np.exp(cumtrapz(radau / top_radius, x=top_radius, initial=0.0))
    epsilon = epsilona * epsilon / epsilon[-1]

    # Output as model attributes
    r = np.zeros(len(top_radius) + 1)
    r[1:] = top_radius
    epsilon = np.insert(epsilon, 0, epsilon[0])  # add a centre of planet value
    v_mod.top_epsilon = epsilon[::-1][:-1]
    v_mod.bot_epsilon = epsilon[::-1][1:]


def get_epsilon(model, depth):
    """
    Gets ellipticity of figure for a model at a specified depth.

    :param model: The tau model object
    :type model: :class:`obspy.taup.tau_model.TauModel`
    :param depth: depth(s) in km
    :type depth: float or :class:`~numpy.ndarray`
    :returns: values of epsilon, ellipticity of figure
    :rtype: :class:`~numpy.ndarray`
    """

    if isinstance(depth, float):
        depth = np.array([depth])

    # Velocity model from TauModel
    v_mod = model.s_mod.v_mod

    # Closest index to depth
    top_layer_idx = v_mod.layer_number_below(0.0)[0]
    layer_idx = top_layer_idx * np.ones(len(depth), dtype=int)
    cond = depth > 0.0
    if cond.any():
        layer_idx[cond] = v_mod.layer_number_above(depth[cond])

    # Interpolate to get epsilon value
    layer = v_mod.layers[layer_idx]
    thick = layer["bot_depth"] - layer["top_depth"]
    bot_eps = v_mod.bot_epsilon[layer_idx]
    top_eps = v_mod.top_epsilon[layer_idx]
    slope = (bot_eps - top_eps) / thick

    return slope * (depth - layer["top_depth"]) + top_eps


def evaluate_derivative_below(model, depth, prop):
    """
    Depth derivative of material property at bottom of a velocity layer.
    """

    # Get the appropriate slowness layer
    layer = model.layers[model.layer_number_below(depth)]
    return evaluate_derivative_at(layer, prop)


def evaluate_derivative_above(model, depth, prop):
    """
    Depth derivative of material property at top of a velocity layer.
    """

    # Get the appropriate slowness layer
    layer = model.layers[model.layer_number_above(depth)]
    return evaluate_derivative_at(layer, prop)


def evaluate_derivative_at(layer, prop):
    """
    Depth derivative of material property in a velocity layer.
    """

    # Get the velocity gradient from the slowness layer
    # Velocity gradient is constant in any slowness layer
    thick = layer["bot_depth"] - layer["top_depth"]
    prop = prop.lower()
    if prop == "p":
        slope = (layer["bot_p_velocity"] - layer["top_p_velocity"]) / thick
        return slope
    if prop == "s":
        slope = (layer["bot_s_velocity"] - layer["top_s_velocity"]) / thick
        return slope
    if prop in "rd":
        slope = (layer["bot_density"] - layer["top_density"]) / thick
        return slope
    raise ValueError("Unknown material property, use p, s, or d.")


def weighted_alp2(m, theta):
    """
    The weighted degree 2 associated Legendre polynomial.

    :param m: order of polynomial (0, 1, or 2)
    :type m: int
    :param theta: angle
    :type theta: float
    :returns: value of weighted associated Legendre polynomial of degree 2
        and order m at x = cos(theta)
    :rtype: float
    """

    # Kronecker delta
    kronecker_0m = 1 if m == 0 else 0

    # Pre-factor for polynomial - Schmidt semi-normalisation
    norm = np.sqrt(
        (2 - kronecker_0m)
        * (np.math.factorial(2 - m) / np.math.factorial(2 + m))
    )

    # Return polynomial of degree 2 and order m
    if m == 0:
        return norm * 0.5 * (3.0 * np.cos(theta) ** 2 - 1.0)
    if m == 1:
        return norm * 3.0 * np.cos(theta) * np.sin(theta)
    if m == 2:
        return norm * 3.0 * np.sin(theta) ** 2
    raise ValueError("Invalid value of m")


def ellipticity_coefficients(arrivals, model=None, lod=EARTH_LOD):
    """
    Ellipticity coefficients for a set of arrivals.

    :param arrivals: TauP Arrivals object with ray paths calculated.
    :type arrivals: :class:`obspy.taup.tau.Arrivals`
    :param model: optional, model used to calculate the arrivals
    :type model: :class:`obspy.taup.tau_model.TauModel`
    :param lod: optional, length of day in seconds. Defaults to Earth value
    :type lod: float
    :returns: list of lists of three floats, ellipticity coefficients
    :rtype: list[list]

    Usage:

    >>> from obspy.taup import TauPyModel
    >>> from ellipticipy.tools import ellipticity_coefficients
    >>> model = TauPyModel('prem')
    >>> arrivals = model.get_ray_paths(source_depth_in_km = 124,
        distance_in_degree = 65, phase_list = ['pPKiKP'])
    >>> ellipticity_coefficients(arrivals)
    [[-0.9322726492103899, -0.6887388908599743, -0.8823671774932877]]
    """


    # If model not specified then obtain via Arrivals
    if model is None:
        model = arrivals.model
        
    # Get coefficients for each arrival individually
    return [
        individual_ellipticity_coefficients(arr, model, lod)
        for arr in arrivals
    ]


def individual_ellipticity_coefficients(arrival, model, lod=EARTH_LOD):
    """
    Ellipticity coefficients for a single ray path.

    :param arrival: TauP Arrival object with ray path calculated.
    :type arrival: :class:`obspy.taup.helper_classes.Arrival`
    :param model: Tau model used to calculate the arrival
    :type model: :class:`obspy.taup.tau_model.TauModel`
    :param lod: optional, length of day in seconds. Defaults to Earth value
    :type lod: float
    :returns: list of three floats, ellipticity coefficients
    :rtype: list
    """

    # Ensure that model is TauModel
    if isinstance(model, TauPyModel):
        model = model.model
    if not isinstance(model, TauModel):
        raise TypeError("Velocity model not correct type")

    # Calculate epsilon values if they don't already exist
    if not hasattr(model.s_mod.v_mod, "top_epsilon"):
        model_epsilon(model, lod)

    # Coefficients from continuous ray path
    ray_sigma = integral_coefficients(arrival, model)

    # Coefficients from discontinuities
    disc_sigma = discontinuity_coefficients(arrival, model)

    # Sum the contribution from the ray path and the discontinuities
    # to get final coefficients
    sigma = [ray_sigma[m] + disc_sigma[m] for m in [0, 1, 2]]

    return sigma


def split_ray_path(arrival, model):
    """
    Split and label ray path according to type of wave.
    """

    # Get discontinuity depths in the model in km
    discs = model.s_mod.v_mod.get_discontinuity_depths()[:-1]

    # Split path at discontinuity depths
    full_path = arrival.path
    depths = full_path["depth"]
    is_disc = np.isin(depths, discs)
    is_disc[0] = False  # Don't split on first point
    idx = np.where(is_disc)[0]

    # Split ray paths, including start and end points
    splitted = np.split(full_path, idx)
    dpaths = [
        np.append(s, splitted[i + 1][0]) for i, s in enumerate(splitted[:-1])
    ]

    # Classify the waves - P or S
    dwaves = [classify_path(path, model) for path in dpaths]

    # Construct final path list by removing diffracted segments
    paths = [p for p, w in zip(dpaths, dwaves) if w != "diff"]
    waves = [w for p, w in zip(dpaths, dwaves) if w != "diff"]

    # Enforce that paths and waves are the same length
    # Something has gone wrong if not
    assert len(paths) == len(waves)

    return paths, waves


def expected_delay_time(ray_param, depth0, depth1, wave, model):
    """
    Expected delay time between two depths for a given wave type (p or s).
    """

    # Convert depths to radii
    radius0 = model.radius_of_planet - depth0
    radius1 = model.radius_of_planet - depth1

    # Velocity model from TauModel
    v_mod = model.s_mod.v_mod

    # Get velocities
    if depth1 >= depth0:
        v0 = v_mod.evaluate_below(depth0, wave)[0]
        v1 = v_mod.evaluate_above(depth1, wave)[0]
    else:
        v0 = v_mod.evaluate_above(depth0, wave)[0]
        v1 = v_mod.evaluate_below(depth1, wave)[0]

    # Calculate time for segment if velocity non-zero
    # - if velocity zero then return zero time
    if v0 > 0.0:

        eta0 = radius0 / v0
        eta1 = radius1 / v1

        def vertical_slowness(eta, p):
            y = eta**2 - p**2
            return np.sqrt(y * (y > 0))  # in s

        n0 = vertical_slowness(eta0, ray_param)
        n1 = vertical_slowness(eta1, ray_param)

        if ray_param == 0.0:
            return 0.5 * ((1.0 / v0) + (1.0 / v1)) * abs(radius1 - radius0)
        return 0.5 * (n0 + n1) * abs(np.log(radius1 / radius0))

    return 0.0


def classify_path(path, model):
    """
    Determine whether we have a p or s-wave path by comparing delay times.
    """

    # Examine just the first two points near the shallowest part of the path
    if path[0]["depth"] < path[-1]["depth"]:
        point0 = path[0]
        point1 = path[1]
    else:
        point0 = path[-2]
        point1 = path[-1]

    # Ray parameter
    ray_param = point0["p"]

    # Depths
    depth0 = point0["depth"]
    depth1 = point1["depth"]

    # If no change in depth then this is a diffracted/head wave segment
    if depth0 == depth1:
        return "diff"

    # Delay time for this segment from ObsPy ray path
    travel_time = point1["time"] - point0["time"]
    distance = abs(point0["dist"] - point1["dist"])
    delay_time = travel_time - ray_param * distance

    # Get the expected delay time for each wave type
    delay_p = expected_delay_time(ray_param, depth0, depth1, "p", model)
    delay_s = expected_delay_time(ray_param, depth0, depth1, "s", model)

    # Difference between predictions and given delay times
    error_p = (delay_p / delay_time) - 1.0
    error_s = (delay_s / delay_time) - 1.0

    # Check which wave type matches the given delay time the best
    if abs(error_p) < abs(error_s):
        return "p"
    return "s"


def integral_coefficients(arrival, model):
    """
    Ellipticity coefficients due to integral along ray path.
    """

    # Split the ray path
    paths, waves = split_ray_path(arrival, model)

    # Loop through path segments
    sigmas = []
    for path, wave in zip(paths, waves):

        # Depth in km
        depth = path["depth"]
        max_depth = np.max(depth)

        # Radius in km
        radius = model.radius_of_planet - depth

        # Velocity in km/s
        v_mod = model.s_mod.v_mod
        cond = depth != max_depth
        v = np.zeros_like(depth)
        v[cond] = v_mod.evaluate_below(depth[cond], wave)
        v[~cond] = v_mod.evaluate_above(max_depth, wave)

        # Gradient of v wrt r in s^-1
        dvdr = np.zeros_like(depth)
        dvdr[cond] = -evaluate_derivative_below(v_mod, depth[cond], wave)
        dvdr[~cond] = -evaluate_derivative_above(v_mod, max_depth, wave)

        # eta in s
        eta = radius / v

        # epsilon
        epsilon = get_epsilon(model, depth)

        # Epicentral distance in radians
        distance = path["dist"]

        # lambda
        lam = [-(2.0 / 3.0) * weighted_alp2(m, distance) for m in [0, 1, 2]]

        # Vertical slowness
        y = eta**2 - arrival.ray_param**2
        vertical_slowness = np.sqrt(y * (y > 0))  # in s

        # Do the integration by trapezoidal rule
        def integration(m):
            integrand = (eta * dvdr / (1.0 - eta * dvdr)) * epsilon * lam[m]
            top = integrand[1:]
            bot = integrand[:-1]
            delta = abs(vertical_slowness[1:] - vertical_slowness[:-1])
            return np.sum(0.5 * (top + bot) * delta)

        sigmas.append([integration(m) for m in [0, 1, 2]])

    # Sum coefficients for each segment to get total ray path contribution
    return [np.sum([s[m] for s in sigmas]) for m in [0, 1, 2]]


def discontinuity_contribution(points, phase, model):
    """
    Ellipticity coefficients due to an individual discontinuity.
    """

    # Use closest points to the boundary
    disc_point = points[0]
    neighbour_point = points[1]

    # Ray parameter
    ray_param = disc_point["p"]

    # Distance in radians
    distance = disc_point["dist"]

    # Radius in km
    depth = disc_point["depth"]
    radius = model.radius_of_planet - depth
    neighbour_depth = neighbour_point["depth"]

    # Get velocity on appropriate side of the boundary
    if neighbour_depth >= depth:
        v = model.s_mod.v_mod.evaluate_below(depth, phase)[0]
    else:
        v = model.s_mod.v_mod.evaluate_above(depth, phase)[0]

    # Vertical slowness
    eta = radius / v
    y = eta**2 - ray_param**2
    vertical_slowness = np.sqrt(y * (y > 0))

    # If ray does not change depth then this should have no contribution
    if neighbour_depth == depth:
        vertical_slowness = 0.0

    # Above/below sign, positive if above
    sign = np.sign(depth - neighbour_depth)

    # epsilon at this depth
    epsilon = get_epsilon(model, depth)

    # lambda at this distance
    lam = [-(2.0 / 3.0) * weighted_alp2(m, distance) for m in [0, 1, 2]]

    # Coefficients for this discontinuity
    sigma = np.array(
        [-sign * vertical_slowness * epsilon * lam[m] for m in [0, 1, 2]]
    )

    return sigma


def discontinuity_coefficients(arrival, model):
    """
    Ellipticity coefficients due to all discontinuities.
    """

    # Split the ray path
    paths, waves = split_ray_path(arrival, model)

    # Loop through path segments
    sigmas = []
    for path, wave in zip(paths, waves):
        start_points = (path[0], path[1])
        end_points = (path[-1], path[-2])

        # Contributions from each end of the ray path segment
        start = discontinuity_contribution(start_points, wave, model)
        end = discontinuity_contribution(end_points, wave, model)

        # Overall contribution
        sigmas.append(start + end)

    # Sum the coefficients from all discontinuities
    disc_sigma = [np.sum([s[m] for s in sigmas]) for m in [0, 1, 2]]

    return disc_sigma


def correction_from_coefficients(coefficients, azimuth, source_latitude):
    """
    Ellipticity correction given the ellipticity coefficients.
    """

    # Convert latitude to colatitude
    colatitude = np.radians(90 - source_latitude)

    # Convert azimuth to radians
    azimuth = np.radians(azimuth)

    return sum(
        coefficients[m] * weighted_alp2(m, colatitude) * np.cos(m * azimuth)
        for m in [0, 1, 2]
    )
