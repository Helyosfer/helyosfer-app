import QtQuick
import QtQuick.Controls
import ".."

// The filled accent button by default; `quiet` gives the outlined secondary
// form and `danger` colors a quiet button for destructive actions.
Button {
    id: control
    property bool quiet: false
    property bool danger: false
    property bool compact: false

    implicitHeight: compact ? 30 : Theme.controlHeight
    leftPadding: compact ? 12 : 16
    rightPadding: compact ? 12 : 16
    font.family: Theme.uiFont
    font.pixelSize: compact ? 12 : 13
    font.weight: Font.DemiBold
    hoverEnabled: true
    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.danger ? Theme.down : (control.quiet ? Theme.text : Theme.onAccent)
        opacity: control.enabled ? 1 : 0.5
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: Theme.controlRadius
        color: control.quiet ? (control.hovered ? Theme.raised : Theme.panel) : Theme.accent
        border.width: control.visualFocus ? 2 : (control.quiet ? 1 : 0)
        border.color: control.visualFocus ? Theme.text : Theme.line
        opacity: !control.enabled ? 0.5 : (control.down ? 0.8 : (control.hovered && !control.quiet ? 0.9 : 1))
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
}
