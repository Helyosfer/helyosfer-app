import QtQuick
import ".."

// Centered column used by the sign-in, setup and onboarding screens.
Rectangle {
    id: root
    default property alias content: column.data
    property string title: ""
    property string subtitle: ""

    color: Theme.page

    Column {
        id: column
        anchors.centerIn: parent
        width: Math.min(380, root.width - 48)
        spacing: 16

        Rectangle {
            width: 40
            height: 40
            radius: 10
            color: Theme.accent

            Text {
                anchors.centerIn: parent
                text: "H"
                color: Theme.onAccent
                font.family: Theme.uiFont
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
        }

        Column {
            width: parent.width
            spacing: 6
            topPadding: 4

            Text {
                width: parent.width
                text: root.title
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 26
                font.weight: Font.Light
                wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                text: root.subtitle
                visible: text.length > 0
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 13
                lineHeight: 1.3
                wrapMode: Text.WordWrap
            }
        }
    }
}
