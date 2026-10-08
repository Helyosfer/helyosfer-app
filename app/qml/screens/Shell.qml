import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Signed-in frame: navigation rail on the left, the selected section on the right.
Rectangle {
    id: root
    property string section: "overview"
    color: Theme.page

    readonly property var sections: [
        { key: "overview", label: "Overview", glyph: "" },
        { key: "assets", label: "Assets", glyph: "" },
        { key: "cards", label: "Cards and accounts", glyph: "" },
        { key: "debts", label: "Debts and payments", glyph: "" },
        { key: "subscriptions", label: "Subscriptions", glyph: "" },
        { key: "tools", label: "Tools", glyph: "" },
        { key: "settings", label: "Settings", glyph: "" }
    ]

    Rectangle {
        id: rail
        width: 216
        height: parent.height
        color: Theme.page

        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: Theme.lineSoft
        }

        Column {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 2

            Row {
                height: 44
                leftPadding: 8
                spacing: 10

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 22; height: 22; radius: 6
                    color: Theme.accent
                    Text {
                        anchors.centerIn: parent
                        text: "H"
                        color: Theme.onAccent
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Helysofer"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
            }

            Item { width: 1; height: 8 }

            Repeater {
                model: root.sections
                NavItem {
                    required property var modelData
                    width: rail.width - 24
                    text: modelData.label
                    glyph: modelData.glyph
                    selected: root.section === modelData.key
                    onClicked: root.section = modelData.key
                }
            }
        }

        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 12
            spacing: 2

            NavItem {
                width: parent.width
                text: Theme.dark ? "Light theme" : "Dark theme"
                glyph: ""
                onClicked: app.toggleTheme()
            }
            NavItem {
                width: parent.width
                text: "Lock"
                glyph: ""
                onClicked: auth.logout()
            }
            Text {
                leftPadding: 10
                topPadding: 8
                text: "Encrypted on this device  ·  " + app.version
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 11
            }
        }
    }

    Loader {
        anchors.left: rail.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        sourceComponent: root.section === "overview" ? overview : pending
    }

    Component { id: overview; Dashboard {} }

    Component {
        id: pending
        Item {
            Column {
                anchors.centerIn: parent
                spacing: 8
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: {
                        for (var i = 0; i < root.sections.length; i++)
                            if (root.sections[i].key === root.section) return root.sections[i].label
                        return ""
                    }
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 22
                    font.weight: Font.Light
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "This section is being built."
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }
            }
        }
    }
}
