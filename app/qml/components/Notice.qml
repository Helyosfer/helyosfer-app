import QtQuick
import ".."

// Inline message under a form. Shakes once when `nudge()` is called.
Text {
    id: root
    property bool problem: true

    visible: text.length > 0
    color: problem ? Theme.down : Theme.muted
    font.family: Theme.uiFont
    font.pixelSize: 13
    wrapMode: Text.WordWrap

    function nudge() { if (Theme.motion) shake.restart() }

    // A new problem draws the eye by itself; the caller need not ask.
    onTextChanged: if (root.problem && root.text.length > 0) root.nudge()

    transform: Translate { id: offset }

    SequentialAnimation {
        id: shake
        NumberAnimation { target: offset; property: "x"; to: 6; duration: 45 }
        NumberAnimation { target: offset; property: "x"; to: -6; duration: 45 }
        NumberAnimation { target: offset; property: "x"; to: 4; duration: 45 }
        NumberAnimation { target: offset; property: "x"; to: 0; duration: 45 }
    }
}
