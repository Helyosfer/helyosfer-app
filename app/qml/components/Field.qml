import QtQuick
import QtQuick.Controls
import ".."

Column {
    id: root
    property alias text: input.text
    property alias placeholder: input.placeholderText
    property alias echoMode: input.echoMode
    property alias input: input
    property string label: ""
    // An amount of money: thousands are grouped while typing, 1000 -> 1.000.
    property bool money: false
    property bool signed: false
    signal accepted()

    spacing: 6

    Text {
        text: root.label
        visible: root.label.length > 0
        color: Theme.muted
        font.family: Theme.uiFont
        font.pixelSize: 12
    }

    TextField {
        id: input
        width: root.width
        implicitHeight: Theme.controlHeight + 4
        leftPadding: 12
        rightPadding: 12
        color: Theme.text
        placeholderTextColor: Theme.faint
        selectionColor: Theme.accent
        selectedTextColor: Theme.onAccent
        font.family: Theme.uiFont
        font.pixelSize: 14
        onAccepted: root.accepted()
        // Erasing a grouping dot would only bring it back; step over it so
        // the key takes the digit beyond it.
        Keys.onPressed: function (event) {
            event.accepted = false
            if (!root.money || selectedText.length > 0) return
            if (event.key === Qt.Key_Backspace && text[cursorPosition - 1] === ".")
                cursorPosition -= 1
            else if (event.key === Qt.Key_Delete && text[cursorPosition] === ".")
                cursorPosition += 1
        }
        onTextEdited: {
            if (!root.money) return
            var masked = app.maskAmount(text, root.signed)
            if (masked === text) return
            // Keep the cursor after the same digits it was after.
            var kept = /[0-9,−-]/
            var before = 0
            for (var i = 0; i < cursorPosition; i++)
                if (kept.test(text[i])) before++
            text = masked
            var position = 0
            for (var seen = 0; position < masked.length && seen < before; position++)
                if (kept.test(masked[position])) seen++
            cursorPosition = position
        }

        background: Rectangle {
            radius: Theme.controlRadius
            color: Theme.panel
            border.width: input.activeFocus ? 2 : 1
            border.color: input.activeFocus ? Theme.accent : Theme.line
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        }
    }
}
