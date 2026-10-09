import QtQuick
import ".."

// Area line chart drawn on a single canvas: no chart library, memory grows
// only with the number of points.
Item {
    id: root
    property var values: []
    // An optional second series drawn behind the first as a muted line.
    property var compare: []
    property var labels: []
    property string emptyText: qsTr("Not enough history to draw yet")
    // With `directional`, the line is green over a span that ends higher
    // than it began and a quiet rose over one that ends lower. A span that
    // ends lower and holds a sharp fall -- a tenth of the balance or more
    // gone between two neighbouring points -- is drawn in the loss red.
    // Otherwise the line is the accent.
    property bool directional: false
    readonly property real sharpFall: 0.10
    readonly property color stroke: {
        if (!directional || values.length < 2) return Theme.accent
        var change = values[values.length - 1] - values[0]
        if (change > 0) return Theme.up
        if (change === 0) return Theme.accent
        for (var i = 1; i < values.length; i++) {
            var fall = values[i - 1] - values[i]
            if (fall > 0 && fall >= Math.abs(values[i - 1]) * sharpFall) return Theme.down
        }
        return Theme.downSoft
    }

    readonly property real padLeft: 52
    readonly property real padBottom: 22
    readonly property real padTop: 8

    onValuesChanged: canvas.requestPaint()
    onStrokeChanged: canvas.requestPaint()
    onCompareChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()

    Connections {
        target: Theme
        function onDarkChanged() { canvas.requestPaint() }
    }

    function shortNumber(value) {
        var magnitude = Math.abs(value)
        if (magnitude >= 1000000) return (value / 1000000).toFixed(1).replace(".", ",") + "M"
        if (magnitude >= 1000) return Math.round(value / 1000) + "k"
        return Math.round(value).toString()
    }

    Text {
        anchors.centerIn: parent
        visible: root.values.length < 2
        text: root.emptyText
        color: Theme.faint
        font.family: Theme.uiFont
        font.pixelSize: 13
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        visible: root.values.length >= 2

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var points = root.values
            if (points.length < 2) return

            var other = root.compare.length === points.length ? root.compare : []
            var low = Math.min.apply(null, points.concat(other))
            var high = Math.max.apply(null, points.concat(other))
            var span = high - low
            var margin = span > 0 ? span * 0.15 : Math.max(Math.abs(high) * 0.05, 1)
            low -= margin
            high += margin

            var left = root.padLeft
            var top = root.padTop
            var plotWidth = width - left - 8
            var plotHeight = height - top - root.padBottom
            function px(index) { return left + plotWidth * index / (points.length - 1) }
            function py(value) { return top + plotHeight * (1 - (value - low) / (high - low)) }

            ctx.font = "10px " + Theme.dataFont
            ctx.textBaseline = "middle"
            for (var step = 0; step <= 3; step++) {
                var value = low + (high - low) * step / 3
                var y = Math.round(py(value)) + 0.5
                ctx.strokeStyle = Theme.lineSoft
                ctx.lineWidth = 1
                ctx.beginPath()
                ctx.moveTo(left, y)
                ctx.lineTo(left + plotWidth, y)
                ctx.stroke()
                ctx.fillStyle = Theme.faint
                ctx.textAlign = "right"
                ctx.fillText(root.shortNumber(value), left - 10, y)
            }

            ctx.textBaseline = "alphabetic"
            ctx.textAlign = "center"
            var every = Math.max(1, Math.ceil(points.length / 6))
            for (var i = 0; i < points.length; i += every) {
                if (root.labels[i] === undefined) continue
                var x = px(i)
                ctx.textAlign = i === 0 ? "left"
                    : (i === points.length - 1 ? "right" : "center")
                ctx.fillText(root.labels[i], x, height - 4)
            }

            var fade = ctx.createLinearGradient(0, top, 0, top + plotHeight)
            fade.addColorStop(0, Qt.rgba(root.stroke.r, root.stroke.g, root.stroke.b, 0.22))
            fade.addColorStop(1, Qt.rgba(root.stroke.r, root.stroke.g, root.stroke.b, 0))
            ctx.beginPath()
            ctx.moveTo(px(0), py(points[0]))
            for (var a = 1; a < points.length; a++) ctx.lineTo(px(a), py(points[a]))
            ctx.lineTo(px(points.length - 1), top + plotHeight)
            ctx.lineTo(px(0), top + plotHeight)
            ctx.closePath()
            ctx.fillStyle = fade
            ctx.fill()

            if (other.length > 0) {
                ctx.beginPath()
                ctx.moveTo(px(0), py(other[0]))
                for (var c = 1; c < other.length; c++) ctx.lineTo(px(c), py(other[c]))
                ctx.strokeStyle = Theme.faint
                ctx.lineWidth = 1.5
                ctx.stroke()
            }

            ctx.beginPath()
            ctx.moveTo(px(0), py(points[0]))
            for (var b = 1; b < points.length; b++) ctx.lineTo(px(b), py(points[b]))
            ctx.strokeStyle = root.stroke
            ctx.lineWidth = 1.75
            ctx.lineJoin = "round"
            ctx.stroke()

            var lastX = px(points.length - 1)
            var lastY = py(points[points.length - 1])
            ctx.beginPath()
            ctx.arc(lastX - 1, lastY, 4, 0, Math.PI * 2)
            ctx.fillStyle = Theme.panel
            ctx.fill()
            ctx.lineWidth = 2
            ctx.stroke()
        }
    }
}
