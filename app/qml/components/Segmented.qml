import QtQuick
import QtQuick.Controls
import ".."

// A row of mutually exclusive options. `model` is a list of {key, label}.
Rectangle {
    id: root
    property var model: []
    property string current: ""
    signal chosen(string key)

    implicitWidth: row.implicitWidth + 2
    implicitHeight: 32
    radius: Theme.controlRadius
    color: "transparent"
    border.width: 1
    border.color: Theme.line

    Row {
        id: row
        anchors.centerIn: parent
        height: parent.height - 2

        Repeater {
            model: root.model

            AbstractButton {
                id: option
                required property var modelData
                required property int index
                readonly property bool selected: modelData.key === root.current

                height: row.height
                implicitWidth: label.implicitWidth + 26
                hoverEnabled: true
                Accessible.name: modelData.label
                onClicked: root.chosen(modelData.key)

                background: Rectangle {
                    color: option.selected ? Theme.accentSoft : (option.hovered ? Theme.raised : "transparent")
                    radius: Theme.controlRadius - 1
                    border.width: option.visualFocus ? 2 : 0
                    border.color: Theme.accent

                    Rectangle {
                        visible: option.index > 0
                        width: 1
                        height: parent.height
                        color: Theme.line
                    }
                }

                contentItem: Text {
                    id: label
                    text: option.modelData.label
                    color: option.selected ? Theme.text : Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
