import QtQuick
import QtQuick.Controls
import ".."

// Modal dialog: title, a column of content, and a footer row of buttons.
Popup {
    id: root
    default property alias content: body.data
    property alias footer: footerRow.data
    property string title: ""
    property string subtitle: ""

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(480, parent ? parent.width - 48 : 480)
    modal: true
    focus: true
    padding: 24
    closePolicy: Popup.CloseOnEscape

    Overlay.modal: Rectangle { color: Theme.dark ? "#b3000000" : "#66121a26" }

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 110 } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 90 } }

    background: Rectangle {
        color: Theme.panel
        radius: Theme.radius + 2
        border.width: 1
        border.color: Theme.line
    }

    contentItem: Column {
        spacing: 16

        Column {
            width: parent.width
            spacing: 4
            Text {
                width: parent.width
                text: root.title
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 20
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
                wrapMode: Text.WordWrap
            }
        }

        Column {
            id: body
            width: parent.width
            spacing: 14
        }

        Row {
            id: footerRow
            anchors.right: parent.right
            spacing: 10
            topPadding: 4
        }
    }
}
