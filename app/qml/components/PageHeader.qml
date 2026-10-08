import QtQuick
import ".."

// Headline figures on the left, the page's main action on the right.
// `figures` is a list of {label, value}.
Item {
    id: root
    property var figures: []
    property string actionText: ""
    signal action()

    height: Math.max(row.height, button.height)

    Row {
        id: row
        spacing: 40

        Repeater {
            model: root.figures
            Column {
                required property var modelData
                spacing: 2
                Text {
                    text: modelData.label
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
                Text {
                    text: modelData.value
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 26
                    font.weight: Font.Light
                }
            }
        }
    }

    PrimaryButton {
        id: button
        visible: root.actionText.length > 0
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: root.actionText
        onClicked: root.action()
    }
}
