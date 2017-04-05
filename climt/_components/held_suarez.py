from sympl import (
    Prognostic, DataArray, replace_none_with_default, combine_dimensions,
    get_numpy_array)
from .._core import get_numpy_arrays_from_state
import numpy as np


class HeldSuarez(Prognostic):
    """
    Provide the Held-Suarez forcing.

    Produces the forcings proposed by Held and Suarez for the intercomparison
    of dynamical cores of AGCMs. Relaxes the temperature field to a zonally
    symmetric equilibrium state, and uses Rayleigh damping of low-level winds
    to represent boundary-layer friction. Details can be found in
    `[Held and Suarez (1994)]`_.

    References:
        Held, I. and M. Suarez, 1994:
            A Proposal for the Intercomparison of the
            Dynamical Cores of Atmospheric General Circulation Models.
            Bull. Amer. Meteor. Soc., 75, 1825-1830,
            doi: 10.1175/1520-0477(1994)075<1825:APFTIO>2.0.CO;2.

    .. _[Held and Suarez (1994)]:
        http://journals.ametsoc.org/doi/pdf/10.1175/1520-0477(1994)075%3C1825%3AAPFTIO%3E2.0.CO%3B2
    """

    inputs = {
        'eastward_wind': 'm s^-1',
        'northward_wind': 'm s^-1',
        'air_temperature': 'degK',
        'air_pressure': 'Pa',
        'surface_air_pressure': 'Pa'}

    tendencies = {
        'eastward_wind': 'm s^-2',
        'northward_wind': 'm s^-2',
        'air_temperature': 'degK s^-1'}

    diagnostics = {}

    def __init__(self,
                 sigma_boundary_layer_top=0.7,
                 k_f=1/86400.,
                 k_a=1/40./86400.,
                 k_s=1/4./86400.,
                 equator_pole_temperature_difference=60,
                 delta_theta_z=10,
                 reference_pressure=None,
                 gas_constant_of_dry_air=None,
                 heat_capacity_of_dry_air_at_constant_pressure=None,
                 planetary_rotation_rate=None,
                 gravitational_acceleration=None,
                 planetary_radius=None):
        """

        Args:
            sigma_boundary_layer_top (float): The height of the boundary
                layer top in sigma coordinates. Corresponds to $\sigma_b$
                in Held and Suarez, 1994. Default is 0.7.

            k_f (float):
                Velocity damping coefficient at the surface in :math:`s^{-1}`.
                Default is :math:`1\ day^{-1}`.

            k_a (float):
                Parameter used in defining vertical profile of the
                temperature damping in :math:`s^{-1}`, as outlined in
                Held and Suarez, 1994.
                Default is :math:`1/40\ day^{-1}`.

            k_s (float):
                Parameter used in defining vertical profile of the
                temperature damping in :math:`s^{-1}`, as outlined in
                Held and Suarez, 1994.
                Default is :math:`1/4\ day^{-1}`.

            equator_pole_temperature_difference (float):
                Equator to pole
                temperature difference, in K.
                Default is 60K.

            delta_theta_z (float):
                Parameter used in defining the equilibrium
                temperature profile as outlined in Held and Suarez, 1994, in K.
                Default is 10K.

            reference_pressure (float):
                Parameter used to define the
                equilibrium temperature profile, roughly equal to the surface
                pressure, in Pa. Default value is :math:`10^5` Pa.

            gas_constant_of_dry_air (float):
                Value in :math:`J kg^{-1} K^{-1}`.
                Default is taken from :code:`sympl.default_constants`.

            heat_capacity_of_dry_air_at_constant_pressure:
                Value in  :math:`J kg^{-1} K^{-1}`.
                Default is taken from :code:`sympl.default_constants`.

            planetary_rotation_rate (float)
                Value in :math:`s^{-1}`.
                Default is taken from :code:`sympl.default_constants`.

            gravitational_acceleration (float):
                Value in :math:`m s^{-2}`.
                Default is taken from :code:`sympl.default_constants`.

            planetary_radius (float):
                Value in :math:`m`.
                Default is taken from :code:`sympl.default_constants`.
        """

        self._sigma_b = sigma_boundary_layer_top
        self._k_f = k_f
        self._k_a = k_a
        self._k_s = k_s
        self._delta_T_y = equator_pole_temperature_difference
        self._delta_theta_z = delta_theta_z

        self._p0 = replace_none_with_default(
            'reference_pressure', reference_pressure)

        self._Cpd = replace_none_with_default(
            'heat_capacity_of_dry_air_at_constant_pressure',
            heat_capacity_of_dry_air_at_constant_pressure)

        self._R_d = replace_none_with_default(
            'gas_constant_of_dry_air', gas_constant_of_dry_air)

        self._kappa = self._R_d/self._Cpd

        self._Omega = replace_none_with_default(
            'planetary_rotation_rate', planetary_rotation_rate)

        self._g = replace_none_with_default(
            'gravitational_acceleration', gravitational_acceleration)

        self._r_planet = replace_none_with_default(
            'planetary_radius', planetary_radius)

        '''
        # cache computed profiles if grid coordinates are given
        if air_pressure is not None and latitude is not None:
            self._Teq = self._get_Teq(latitude, air_pressure)
        else:
            self._Teq = None

        if latitude is not None and sigma is not None:
            self._k_t = self._get_k_t(latitude, sigma)
        else:
            self._k_t = None

        if sigma is not None:
            self._k_v = self._get_k_v(sigma)
        else:
            self._k_v = None
        self.inputs = ['eastward_wind', 'northward_wind', 'air_temperature']
        if sigma is None:
            self.inputs.append('sigma')
        if latitude is None:
            self.inputs.append('latitude')
        if air_pressure is None:
            self.inputs.append('air_pressure')
        self.inputs = tuple(self.inputs)
        '''

    def __call__(self, state):
        """
        Get the Held-Suarez forcing tendencies

        Args:
            state (dict): A model state dictionary.

        Returns:
            tendencies (dict), diagnostics (dict):

            * A dictionary whose keys are strings indicating
              state quantities and values are the time derivative of those
              quantities in units/second at the time of the input state.
            * A dictionary whose keys are strings indicating
              state quantities and values are the value of those quantities
              at the time of the input state.

        Raises:
            IndexError:
                if the input state does not contain the key :code:`latitude`.
        """

        if 'latitude' not in state:
            raise IndexError('state must contain a quantity labeled "latitude"')

        sigma = state['air_pressure']/state['surface_air_pressure']
        sigma.attrs['units'] = ''

        Teq = self._get_Teq(state['latitude'], state['air_pressure'])
        k_t = self._get_k_t(state['latitude'], sigma)
        k_v = self._get_k_v(sigma)

        input_arrays = get_numpy_arrays_from_state(self, 'inputs', state)

        tendencies = {
            'eastward_wind': DataArray(
                - k_v.values * input_arrays['eastward_wind'],
                dims=combine_dimensions(
                    [k_v, state['eastward_wind']], out_dims=('x', 'y', 'z')),
                attrs={'units': 'm s^-2'}).squeeze(),

            'northward_wind': DataArray(
                - k_v.values * input_arrays['northward_wind'],
                dims=combine_dimensions(
                    [k_v, state['northward_wind']], out_dims=('x', 'y', 'z')),
                attrs={'units': 'm s^-2'}).squeeze(),

            'air_temperature': DataArray(
                - k_t.values * (input_arrays['air_temperature'] - Teq.values),
                dims=combine_dimensions(
                    [k_t, state['air_temperature']], out_dims=('x', 'y', 'z')),
                attrs={'units': 'K s^-1'}).squeeze()
        }

        return tendencies, {}

    def _get_Teq(self, latitude, air_pressure):

        out_dims = combine_dimensions(
            [latitude, air_pressure], out_dims=('x', 'y', 'z'))

        latitude = get_numpy_array(
            latitude.to_units('degrees_N'), out_dims=('x', 'y', 'z'))

        air_pressure = get_numpy_array(
            air_pressure.to_units('Pa'), out_dims=('x', 'y', 'z'))

        return DataArray(np.maximum(
            200,
            (315 - self._delta_T_y*np.sin(latitude)**2 -
             self._delta_theta_z*np.log(air_pressure/self._p0.values)*np.cos(latitude)**2
             ) * (air_pressure/self._p0.values)**self._kappa.values),
            dims=out_dims,
            attrs={'units': 'degK'})

    def _get_k_t(self, latitude, sigma):

        out_dims = combine_dimensions([latitude, sigma], out_dims=('x', 'y', 'z'))

        latitude = get_numpy_array(
            latitude.to_units('degrees_N'), out_dims=('x', 'y', 'z'))

        sigma = get_numpy_array(sigma, out_dims=('x', 'y', 'z'))

        return DataArray(
            self._k_a +
            (self._k_s - self._k_a) *
            np.maximum(0, (sigma - self._sigma_b)/(1 - self._sigma_b)) *
            np.cos(latitude)**4,
            dims=out_dims,
            attrs={'units': 's^-1'})

    def _get_k_v(self, sigma):

        out_dims = combine_dimensions([sigma], out_dims=('x', 'y', 'z'))

        sigma = get_numpy_array(sigma.to_units(''), out_dims=('x', 'y', 'z'))

        return DataArray(
            self._k_f * np.maximum(
                0,
                (sigma - self._sigma_b)/(1 - self._sigma_b)),
            dims=out_dims,
            attrs={'units': 's^-1'})
