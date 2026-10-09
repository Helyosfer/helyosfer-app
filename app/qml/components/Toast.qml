import QtQuick
import ".."

// A short confirmation that rises from the bottom edge, stays a moment and
// leaves by itself. It never takes focus and needs no answer.
Rectangle {
    id: root

    function show(message) {
        label.text = message
        leaving.stop()
        arriving.restart()
        stay.restart()
    }

    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 28
    z: 900
    width: row.implicitWidth + 32
    height: 38
    radius: 19
    color: Theme.raised
    border.width: 1
    border.color: Theme.line
    opacity: 0
    visible: opacity > 0
    transform: Translate { id: lift }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 9

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: ""
            color: Theme.up
            font.family: Theme.iconFont
            font.pixelSize: 13
        }
        Text {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: 13
        }
    }

    ParallelAnimation {
        id: arriving
        NumberAnimation { target: root; property: "opacity"; to: 1; duration: Theme.medium }
        NumberAnimation { target: lift; property: "y"; from: 14; to: 0; duration: Theme.medium; easing.type: Easing.OutCubic }
    }
    Timer { id: stay; interval: 1900; onTriggered: leaving.restart() }
    ParallelAnimation {
        id: leaving
        NumberAnimation { target: root; property: "opacity"; to: 0; duration: Theme.medium }
        NumberAnimation { target: lift; property: "y"; to: 8; duration: Theme.medium }
    }
}
