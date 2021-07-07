import sys
from array import array
import numpy as np
from scipy.signal import butter, filtfilt

import conf as conf


class Person:
    """
    State and heart rate calculations for one person.
    """

    def __init__(self, face):
        self.face = face  # face region
        self.prevFace = None  # previous face region
        self.correction = 1.0  # correction for switching face regions
        self.times = array('d')  # sample times
        self.raw = array('d')  # spatial-averaged raw sensor samples
        self.corrected = array('d')  # raw values corrected for ROI changes
        self.filtered = array('d')  # bandpass filtered
        self.bpm = array('d')  # beats per minute
        self.avBpm = array('d')  # slow running average of beats per minute
        self.spectrum = []  # spectral power
        self.freqs = []  # frequencies in bpm
        self._firstTime = 0.0
        self._index = 0
        self.sp = array('d')
        self.dp = array('d')
        self.avg_sp = array('d')
        self.avg_dp = array('d')
        self.pheight = 0.0
        self.pweight = 0.0
        self.age = 0

    def setBoilerPlate(self, weight, height, age):
        self.pheight = height
        self.pweight = weight
        self.age = age

    def setFace(self, face):
        """
        Set new face region.
        """
        self.prevFace = self.face
        self.face = face

    def append_lastest_sp_dp(self, sp, dp):
        """
        Sets the blood pressure formats.
        """
        self.sp.append(sp)
        self.dp.append(dp)

    def contains(self, x, y):
        """
        Does this person's face contain the given point?
        """
        xf, yf, wf, hf = self.face
        return xf <= x <= xf + wf and yf <= y <= yf + hf

    def  _blood_pressure_calculator(self, avg_bpm):
        """
        returns sp, dp
        """
        kgs = self.pweight * 0.45359237  # lbs to kgs
        cm = self.pheight / 0.39370  # in to cm
        q = 4.5  # constant

        rob = 18.5
        et = (364.5 - 1.23 * avg_bpm)
        bsa = 0.007184 * (kgs ** 0.425) * (cm ** 0.725)
        sv = (-6.6 + (0.25 * (et - 35)) - (0.62 * avg_bpm) + (40.4 * bsa) - (0.51 * self.age))
        pp = sv / ((0.013 * kgs - 0.007 * self.age - 0.004 * avg_bpm) + 1.307)
        mpp = q * rob

        sp = int(mpp + 3 / 2 * pp)
        dp = int(mpp - pp / 3)

        return sp, dp

    def _blood_pressure_calculator(self, avg_bpm, weight, height, age):

        kgs = weight * 0.45359237  # lbs to kgs
        cm = height / 0.39370  # in to cm
        q = 4.5  # constant

        rob = 18.5
        et = (364.5 - 1.23 * avg_bpm)
        bsa = 0.007184 * (kgs ** 0.425) * (cm ** 0.725)
        sv = (-6.6 + (0.25 * (et - 35)) - (0.62 * avg_bpm) + (40.4 * bsa) - (0.51 * age))
        pp = sv / ((0.013 * kgs - 0.007 * age - 0.004 * avg_bpm) + 1.307)
        mpp = q * rob

        sp = int(mpp + 3 / 2 * pp)
        dp = int(mpp - pp / 3)

        return sp, dp

    def analyze(self, t, greenIm):
        """
        Add new green channel frame to be analyzed.
        """
        if not self._firstTime:
            self._firstTime = t
        if t < self._firstTime + conf.STARTUP_TIME:
            return
        for arr in (
                self.times, self.raw, self.corrected, self.bpm, self.avBpm):
            if len(arr) >= conf.MAX_SAMPLES:
                arr.pop(0)

        self.times.append(t)
        raw = self._getSignal(greenIm, self.face)
        self.raw.append(raw)

        if self.prevFace is not None:
            prev = self._getSignal(greenIm, self.prevFace)
            self.correction *= prev / raw
            self.prevFace = None
        self.corrected.append(raw * self.correction)

        fps = self._getFPS()
        nyquistFreq = 0.5 * fps
        self.filtered = self._filter(self.corrected, nyquistFreq)
        if not len(self.filtered):
            return

        self.freqs, self.spectrum = self._createSpectrum(
            self.filtered, nyquistFreq)
        bpm = self._findPeak(self.freqs, self.spectrum)
        if conf.MIN_BPM <= bpm <= conf.MAX_BPM:
            sp, dp = self._blood_pressure_calculator(bpm)
            self.sp.append(sp)
            self.dp.append(dp)
            self.bpm.append(bpm)
            self._index += 1
            if fps:
                p = int(0.5 + conf.AV_BPM_PERIOD * fps)
                if len(self.bpm) == conf.MAX_SAMPLES and not self._index % p:
                    av = np.average(self.bpm[-p:])
                    self.avBpm.append(av)
                    self.avg_sp.append(sp)
                    self.avg_dp.append(dp)

    def _getSignal(self, greenIm, face):
        """
        Acquire a signal sample by averaging over a ROI in the green channel.
        """
        x, y, w, h = [int(i) for i in face]
        forehead = greenIm[y:y + h // 4, x:x + w]
        nose = greenIm[y + h // 2:y + (3 * h) // 4, x:x + w]
        n = forehead.size + nose.size
        s = forehead.sum() + nose.sum() if n else 0
        return s / n if n else 128.0

    def _getFPS(self):
        """
        Get average number of frames per second.
        """
        sz = len(self.times)
        if sz >= 2:
            t0 = self.times[0]
            t1 = self.times[-1]
            fps = (sz - 1) / (t1 - t0)
        else:
            fps = 0.0
        return fps

    def _filter(self, data, nyquistFreq):
        """
        Apply time interpolation and 3th order Butterworth bandpass filter.
        """
        sz = len(data)
        if sz < 22:
            # butterworth filter needs at least this number of samples
            return []

        t0 = self.times[0]
        t1 = self.times[-1]
        times = np.linspace(t0, t1, sz)
        interpolated = np.interp(times, self.times, data)

        r = [
            min(1, bpm / 60 / nyquistFreq)
            for bpm in (conf.MIN_BPM, conf.MAX_BPM)]
        b, a = butter(3, r, btype='bandpass')
        filtered = filtfilt(b, a, interpolated)
        return filtered

    def _createSpectrum(self, data, nyquistFreq):
        """
        Calculate interpolated power spectrum density from the given data.
        Return 2-tuple of freqs and spectrum arrays.
        """
        data = data * np.hanning(len(data))
        fft = np.fft.rfft(data, n=8 * len(data))
        spectrum = np.abs(fft)
        freqs = np.linspace(0, nyquistFreq * 60, len(spectrum))
        idx = np.where((freqs >= conf.MIN_BPM) & (freqs <= conf.MAX_BPM))
        freqs = freqs[idx]
        spectrum = spectrum[idx]
        spectrum /= np.max(spectrum)
        spectrum **= 2
        return freqs, spectrum

    def _findPeak(self, x, y):
        """
        Find interpolated location of the highest peak.
        """
        peak = 0
        maxBin = np.argmax(y)
        threshold = y.max() / 2
        if 0 < maxBin < len(y) - 1:
            # find bins around peak that are at least half the peak hight
            leftBin, rightBin = -1, -1
            for leftBin in range(maxBin, 0, -1):
                if y[leftBin - 1] < threshold:
                    break
            for rightBin in range(maxBin, len(y) - 1):
                if y[rightBin + 1] < threshold:
                    break
            # parabolic fit of peak
            if leftBin >= 0 and rightBin >= 0:
                s = np.arange(leftBin, rightBin + 1)
                a, b, c = np.polyfit(x[s], y[s], 2)
                peak = -0.5 * b / a if a != 0 else -2
                if peak < x[maxBin - 1] or peak > x[maxBin + 1]:
                    # parabolic fit failed
                    peak = x[maxBin]
        else:
            peak = x[maxBin]
        return peak
