# Functions freq_array, aperture_function, are adopted from Hyperspy
# and are subject of following copyright:
#
#  Copyright 2007-2016 The HyperSpy developers
#
#  HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  HyperSpy.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright 2019 The LiberTEM developers
#
#  LiberTEM is distributed under the terms of the GNU General
# Public License as published by the Free Software Foundation,
# version 3 of the License.
# see: https://github.com/LiberTEM/LiberTEM

import numpy as np

from libertem.udf import UDF

import numba

from skimage.draw import polygon


def freq_array(shape, sampling=(1., 1.)):
    """
    Makes up a frequency array.

    Parameters
    ----------
    shape : (int, int)
        The shape of the array.
    sampling: (float, float), optional, (Default: (1., 1.))
        The sampling rates of the array.
    Returns
    -------
        Array of the frequencies.
    """
    f_freq_1d_y = np.fft.fftfreq(shape[0], sampling[0])
    f_freq_1d_x = np.fft.fftfreq(shape[1], sampling[1])
    f_freq_mesh = np.meshgrid(f_freq_1d_x, f_freq_1d_y)
    f_freq = np.hypot(f_freq_mesh[0], f_freq_mesh[1])

    return f_freq


def aperture_function(r, apradius, rsmooth):
    """
    A smooth aperture function that decays from apradius-rsmooth to apradius+rsmooth.
    Parameters
    ----------
    r : ndarray
        Array of input data (e.g. frequencies)
    apradius : float
        Radius (center) of the smooth aperture. Decay starts at apradius - rsmooth.
    rsmooth : float
        Smoothness in halfwidth. rsmooth = 1 will cause a decay from 1 to 0 over 2 pixel.
    Returns
    -------
        2d array containing aperture
    """

    # TODO： The aperture can be not only a circle and has to be extended into other geometry, like ellipse.

    return 0.5 * (1. - np.tanh((np.absolute(r) - apradius) / (0.5 * rsmooth)))


def line_filter(size, sidebandpos, width, length):
    """
    A line filter function that is used to remove Fresnel fringes from biprism. 
    ----------
    size : 2d tuple, ()
        size of the FFT of the hologram.
    sidebandpos : 2d tuple, ()
        Position of the sideband that is used for reconstruction of holograms.
    width: float
        Width of the line (rectangle).
    length : float
        Length of the line (rectangle).
    Returns
    -------
        2d array containing line filter
    """

    angle = np.arctan2(size[0] / 2 + 1 - sidebandpos[0],  size[1] / 2 + 1 - sidebandpos[1])
    left_bottom = ((size[0] / 2 + 1 + sidebandpos[0] + width) / 2, (size[1] / 2 + 1 + sidebandpos[1]) / 2)

    right_bottom = (left_bottom[0] + np.cos(angle) * length, left_bottom[1] + np.sin(angle) * length)
    left_top = (left_bottom[0] - np.sin(angle) * width, left_bottom[1] + np.cos(angle) * width)
    right_top = (right_bottom[0] + left_top[0] - left_bottom[0], right_bottom[1] + left_top[1] - left_bottom[1])

    r = np.array([left_bottom[0],right_bottom[0],right_top[0],left_top[0]],dtype=int)
    c = np.array([left_bottom[1],right_bottom[1],right_top[1],left_top[1]],dtype=int)
    rr, cc = polygon(r, c)

    mask = np.ones(size)
    mask[rr,cc] = 0

    return mask


def phase_ramp_finding(img, order=1):
    """
    A phase ramp finding function that is used to find the phase ramp across the field of view. 
    ----------
    img : 2d nd array
        Complex image or phase image.
    order : int
        Phase ramp, 1 (default) is linear.
    ramp : 2d tuple, ()
        Phase ramp in x, y, if not None.
    Returns
    -------
        ramp, order, tuple, float
    """

    # The ramp is determined by the maximum and minimum values of the image.
    # TODO least-square-fitting, polynomial order
    if order==1:
        ramp_x = np.mean(np.gradient(img, axis=0))
        ramp_y = np.mean(np.gradient(img, axis=1))
        ramp = (ramp_y, ramp_x)
    else:
        pass

    return ramp

def phase_ramp_removal(size, order=1, ramp=None):
    """
    A phase ramp removal function that is remove to find the phase ramp across the field of view. 
    ----------
    size : 2d tuple, ()
        Size of the Complex image or phase image
    order : int
        Phase ramp, 1 (default) is linear.
    ramp : 2d tuple, ()
        Phase ramp in x, y, if not None.
    Returns
    -------
        2d nd array of the corrected image
    """
    img = np.zeros(size)

    if ramp is None:
        ramp = phase_ramp_finding(size, order=1)
    else:
        (ramp_y, ramp_x) = ramp

    yy = np.arange(0, size[0], 1)
    xx = np.arange(0, size[1], 1)      
    y, x = np.meshgrid(yy, xx)

    if order==1:
        img =  ramp_x * x + ramp_y * y
    else:
        # To be expanded.
        pass

    return img

class HoloReconstructUDF(UDF):
    """
    Reconstruct off-axis electron holograms using a Fourier-based method.

    Running :meth:`~libertem.api.Context.run_udf` on an instance of this class
    will reconstruct a complex electron wave. Use the :code:`wave` key to access
    the raw data in the result.

    See :ref:`holography app` for detailed application example

    .. versionadded:: 0.3.0

    Examples
    --------
    >>> shape = tuple(dataset.shape.sig)
    >>> sb_position = [2, 3]
    >>> sb_size = 4.4
    >>> holo_udf = HoloReconstructUDF(out_shape=shape,
    ...                               sb_position=sb_position,
    ...                               sb_size=sb_size)
    >>> wave = ctx.run_udf(dataset=dataset, udf=holo_udf)['wave'].data
    """

    def __init__(self,
                 out_shape,
                 sb_position,
                 sb_size,
                 sb_smoothness=.05,
                 precision=True):
        """
        out_shape : (int, int)
            Shape of the returned complex wave image. Note that the result should fit into the
            main memory.
            See :ref:`holography app` for more details

        sb_position : tuple, or vector
            Coordinates of sideband position with respect to non-shifted FFT of a hologram

        sb_size : float
            Radius of side band filter in pixels

        sb_smoothness : float, optional (Default: 0.05)
            Fraction of `sb_size` over which the edge of the filter aperture to be smoothed

        precision : bool, optional, (Default: True)
            Defines precision of the reconstruction, True for complex128 for the resulting
            complex wave, otherwise results will be complex64
        """
        super().__init__(out_shape=out_shape,
                         sb_position=sb_position,
                         sb_size=sb_size,
                         sb_smoothness=sb_smoothness,
                         precision=precision)

    def get_result_buffers(self):
        """
        Initializes :class:`~libertem.common.buffers.BufferWrapper` objects for reconstructed
        wave function

        Returns
        -------
        A dictionary that maps 'wave' to the corresponding
        :class:`~libertem.common.buffers.BufferWrapper` objects
        """
        extra_shape = self.params.out_shape
        if not self.params.precision:
            dtype = np.complex64
        else:
            dtype = np.complex128
        return {
            "wave": self.buffer(kind="nav", dtype=dtype, extra_shape=extra_shape)
        }

    def get_task_data(self):
        """
        Updates `task_data`

        Returns
        -------
        kwargs : dict
        A dictionary with the following keys:
            kwargs['aperture'] : array-like
            Side band filter aperture (mask)
            kwargs['slice'] : slice
            Slice for slicing FFT of the hologram
        """

        out_shape = self.params.out_shape
        sy, sx = self.meta.partition_shape.sig
        oy, ox = out_shape
        f_sampling = (1. / oy, 1. / ox)
        sb_size = self.params.sb_size * np.mean(f_sampling)
        sb_smoothness = sb_size * self.params.sb_smoothness * np.mean(f_sampling)

        f_freq = freq_array(out_shape)
        aperture = aperture_function(f_freq, sb_size, sb_smoothness)

        y_min = int(sy / 2 - oy / 2)
        y_max = int(sy / 2 + oy / 2)
        x_min = int(sx / 2 - ox / 2)
        x_max = int(sx / 2 + oy / 2)
        slice_fft = (slice(y_min, y_max), slice(x_min, x_max))

        kwargs = {
            'aperture': self.xp.array(aperture),
            'slice': slice_fft
        }
        return kwargs

    def process_frame(self, frame):
        """
        Reconstructs holograms outputting results into 'wave'

        Parameters
        ----------
        frame
           single frame (hologram) of the data
        """
        if not self.params.precision:
            frame = frame.astype(np.float32)
        # size_x, size_y = self.params.out_shape
        frame_size = self.meta.partition_shape.sig
        sb_pos = self.params.sb_position
        aperture = self.task_data.aperture
        slice_fft = self.task_data.slice

        fft_frame = self.xp.fft.fft2(frame) / np.prod(frame_size)
        fft_frame = self.xp.roll(fft_frame, sb_pos, axis=(0, 1))

        fft_frame = self.xp.fft.fftshift(self.xp.fft.fftshift(fft_frame)[slice_fft])

        fft_frame = fft_frame * aperture

        wav = self.xp.fft.ifft2(fft_frame) * np.prod(frame_size)
        # FIXME check if result buffer with where='device' and export is faster
        # than exporting frame by frame, as implemented now.
        if self.meta.device_class == 'cuda':
            # That means xp is cupy
            wav = self.xp.asnumpy(wav)
        self.results.wave[:] = wav

    def get_backends(self):
        # CuPy support deactivated due to https://github.com/LiberTEM/LiberTEM/issues/815
        return ('numpy',)
        # return ('numpy', 'cupy')
