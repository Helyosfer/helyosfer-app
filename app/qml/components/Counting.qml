import QtQuick
import ".."

// Text that holds a figure. When the figure changes it counts its way from
// the old value to the new one instead of being replaced. Anything that is
// not a figure ("—", a word) is shown as it is.
Text {
    id: root

    // What to show, written as the application writes amounts:
    // "1.250,50 ₺", "+38.760,00 ₺", "81".
    property string value: ""

    // A name for this place on screen. With one, the figure counts on from
    // what the place showed before, even if this item was just created.
    property string place: ""

    property real counted: 0
    // The parts of the current figure: what stands before the digits, how
    // many decimals it has, what follows.
    property var shape: null

    function read(text) {
        var match = /^([^0-9]*)([0-9][0-9.]*)(?:,([0-9]+))?(.*)$/.exec(text)
        if (!match) return null
        var decimals = match[3] === undefined ? "" : match[3]
        var number = parseFloat(match[2].replace(/\./g, "") + (decimals.length ? "." + decimals : ""))
        if (isNaN(number)) return null
        return { before: match[1], number: number, decimals: decimals.length, after: match[4] }
    }

    function write(number) {
        var parts = Math.abs(number).toFixed(shape.decimals).split(".")
        var whole = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".")
        return shape.before + whole + (shape.decimals > 0 ? "," + parts[1] : "") + shape.after
    }

    // `value` and `place` are both set while the item is being created, in
    // no promised order, so the first figure is taken up once both are there.
    property bool ready: false
    Component.onCompleted: { ready = true; take() }
    onValueChanged: if (ready) take()

    // The place remembers what it is showing right now, not where it is
    // heading: an item created in the middle of a count carries on from there.
    onCountedChanged: {
        if (place.length > 0 && shape !== null)
            Theme.figures[place] = { before: shape.before, after: shape.after,
                                     decimals: shape.decimals, number: counted }
    }

    function take() {
        var previous = shape
        var next = read(value)
        if (previous === null && place.length > 0 && Theme.figures[place] !== undefined) {
            previous = Theme.figures[place]
            counted = previous.number
        }
        shape = next
        if (next === null) { run.stop(); return }
        // Counting needs a figure before and after that are written alike;
        // a change of sign or of unit is shown at once.
        var alike = previous !== null && previous.before === next.before
            && previous.after === next.after && previous.decimals === next.decimals
        if (!alike || Theme.slow === 0) {
            run.stop()
            counted = next.number
            return
        }
        run.from = counted
        run.to = next.number
        run.restart()
    }

    text: shape === null ? value : write(counted)

    NumberAnimation {
        id: run
        target: root
        property: "counted"
        duration: Theme.slow * 1.5
        easing.type: Easing.OutCubic
    }
}
