import QtQuick
import QtQuick.Controls
import ".."

AbstractButton {
    id: control
    property string glyph: ""
    property bool selected: false
    // Off where something else marks the chosen entry.
    property bool marked: true

    implicitHeight: 36
    hoverEnabled: true
    Accessible.name: text

    background: Rectangle {
        radius: Theme.controlRadius
        color: control.selected && control.marked ? Theme.accentSoft
            : (control.hovered && !control.selected ? Theme.raised : "transparent")
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        border.width: control.visualFocus ? 2 : 0
        border.color: Theme.accent
    }

    contentItem: Row {
        leftPadding: 10
        spacing: 10

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: control.glyph
            font.family: Theme.iconFont
            font.pixelSize: 15
            color: control.selected ? Theme.accent : Theme.muted
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: control.text
            font.family: Theme.uiFont
            font.pixelSize: 13
            font.weight: Font.Medium
            color: control.selected || control.hovered ? Theme.text : Theme.muted
        }
    }
}
