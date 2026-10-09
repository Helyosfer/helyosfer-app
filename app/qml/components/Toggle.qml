import QtQuick
import QtQuick.Controls
import ".."

Switch {
    id: control
    font.family: Theme.uiFont
    font.pixelSize: 13
    spacing: 10
    padding: 0

    indicator: Rectangle {
        implicitWidth: 34
        implicitHeight: 20
        y: (control.height - height) / 2
        radius: 10
        color: control.checked ? Theme.accent : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? Theme.text : (control.checked ? Theme.accent : Theme.line)

        Rectangle {
            width: 14
            height: 14
            radius: 7
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: control.checked ? Theme.onAccent : Theme.muted
            Behavior on x { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        font: control.font
        color: Theme.text
        opacity: control.enabled ? 1 : 0.5
        verticalAlignment: Text.AlignVCenter
    }
}
