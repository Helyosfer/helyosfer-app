import QtQuick
import QtQuick.Controls
import ".."

Button {
    id: control
    property bool quiet: false

    implicitHeight: Theme.controlHeight
    leftPadding: 16
    rightPadding: 16
    font.family: Theme.uiFont
    font.pixelSize: 13
    font.weight: Font.DemiBold
    hoverEnabled: true

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.quiet ? Theme.text : Theme.onAccent
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
    }
}
