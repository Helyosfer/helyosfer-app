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

    readonly property int currentIndex: {
        for (var i = 0; i < model.length; i++) if (model[i].key === current) return i
        return -1
    }

    // The marker under the chosen option; it travels when the choice changes.
    Rectangle {
        id: marker
        readonly property Item chosenItem: root.currentIndex >= 0 ? options.itemAt(root.currentIndex) : null
        visible: chosenItem !== null
        x: row.x + (chosenItem ? chosenItem.x : 0)
        y: row.y
        width: chosenItem ? chosenItem.width : 0
        height: row.height
        radius: Theme.controlRadius - 1
        color: Theme.accentSoft
        Behavior on x { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutCubic } }
    }

    Row {
        id: row
        anchors.centerIn: parent
        height: parent.height - 2

        Repeater {
            id: options
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
                    color: !option.selected && option.hovered ? Theme.raised : "transparent"
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
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
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
