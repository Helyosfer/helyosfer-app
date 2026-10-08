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

        background: Rectangle {
            radius: Theme.controlRadius
            color: Theme.panel
            border.width: input.activeFocus ? 2 : 1
            border.color: input.activeFocus ? Theme.accent : Theme.line
        }
    }
}
