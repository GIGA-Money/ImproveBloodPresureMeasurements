import PyQt5.Qt as qt
import PyQt5.Qt as qt
from plot import Plot
from plot import Plot
import util as util
import util as util
from widgets import View, CurveWidget


class View(qt.QWidget):
    """
    Video canvas with overlay.
    """

    def __init__(self, parent):
        qt.QWidget.__init__(self, parent)
        self.image = None

    def draw(self, im, persons):
        """
        Display the CV2 image with overlay from the analysed persons.
        """
        qim = util.qImage(im)
        with qt.QPainter(qim) as p:
            for person in persons:
                x, y, w, h = person.face
                p.setPen(qt.QColor(255, 255, 255, 64))
                p.drawRect(x, y, w, h / 4)
                p.drawRect(x, y + h / 2, w, h / 4)
                font = p.font()
                font.setPixelSize(18)
                p.setFont(font)
                p.setPen(qt.QColor(255, 255, 255))
                bpm = person.avBpm[-1] if len(person.avBpm) else 0
                sp = person.avg_sp[-1] if len(person.avg_sp) else 0
                dp = person.avg_dp[-1] if len(person.avg_dp) else 0
                bp = "{}/{}".format(str(int(sp)), str(int(dp)))
                p.drawText(
                    x, y, w, h, qt.Qt.AlignHCenter, '♡' + str(int(bpm)))
                p.drawText(
                    x, y + h / 2, w, h / 4, qt.Qt.AlignHCenter, bp)
        self.image = qim
        self.setMinimumSize(qim.size())
        self.update()

    def paintEvent(self, ev):
        if self.image:
            with qt.QPainter(self) as p:
                p.drawImage(0, 0, self.image)


class CurveWidget(qt.QSplitter):
    """
    Realtime curves.
    """

    def __init__(self, parent=None):
        qt.QSplitter.__init__(self, qt.Qt.Vertical, parent=parent)
        self.setMinimumHeight(640)
        self.image = None
        self.plots = [Plot(title=t) for t in (
            'Signal', 'Filtered', 'Spectrum', 'BPM', "Blood Pressure Sp", "Blood Pressure Dp")]
        for plot in self.plots:

        self.bp_plots = [Plot(title=t) for t in ('SP', 'DP')]
        for plot in self.bp_plots:
            self.addWidget(plot)

    def plot(self, persons):
        """
        Update plots with newest data from the persons.
        """
        for plot in self.plots:
            plot.clear()
        raw, filtered, spectrum, bpm, bp_sp, bp_dp = self.plots
        for person in persons:
            raw.plot(person.corrected)
        for person in persons:
            filtered.plot(person.filtered)
        for person in persons:
            spectrum.plot(person.spectrum, x=person.freqs)
        for person in persons:
            bpm.plot(person.bpm)
            bpm.plot(person.avBpm, pen=qt.Qt.red)
        for person in persons:
            bp_sp.plot(person.sp)
            bp_dp.plot(person.dp, pen=qt.Qt.blue)
