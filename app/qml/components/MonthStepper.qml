import QtQuick
import ".."

// "‹  October 2026  ›"
Row {
    id: root
    property string title: ""
    signal previous()
    signal next()

    spacing: 8

    PrimaryButton {
        compact: true; quiet: true
        width: 32
        leftPadding: 0; rightPadding: 0
        text: "‹"
        Accessible.name: qsTr("Previous month")
        onClicked: root.previous()
    }
    Text {
        anchors.verticalCenter: parent.verticalCenter
        width: 150
        horizontalAlignment: Text.AlignHCenter
        text: root.title
        color: Theme.text
        font.family: Theme.uiFont
        font.pixelSize: 14
        font.weight: Font.DemiBold
    }
    PrimaryButton {
        compact: true; quiet: true
        width: 32
        leftPadding: 0; rightPadding: 0
        text: "›"
        Accessible.name: qsTr("Next month")
        onClicked: root.next()
    }
}
