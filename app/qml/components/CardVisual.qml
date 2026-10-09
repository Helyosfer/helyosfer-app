import QtQuick
import ".."

// A credit card drawn as the object it is. It leans toward the pointer, a
// band of light crosses it when it appears, and where `flippable` is set a
// click turns it over to show what is printed on the back.
Item {
    id: root

    property string holder: ""
    // Digits being typed, for a live preview; when empty the card shows
    // `lastFour` behind dots, the way a saved card is kept.
    property string digits: ""
    property string lastFour: ""
    property string network: ""
    property bool frozen: false
    property bool flippable: false
    property bool flipped: false
    // What the back shows: a list of { label, value }.
    property var details: []

    implicitWidth: 300
    implicitHeight: Math.round(width / 1.586)

    readonly property real unit: width / 300
    readonly property string shownNumber: {
        var groups = []
        if (digits.length > 0) {
            var typed = digits.substring(0, 16)
            while (typed.length < 16) typed += "•"
            for (var i = 0; i < 16; i += 4) groups.push(typed.substring(i, i + 4))
        } else {
            groups = ["••••", "••••", "••••", lastFour.length === 4 ? lastFour : "••••"]
        }
        return groups.join("  ")
    }

    // Plays the arrival again, for a card that was hidden and is shown anew.
    function play() {
        arrival.restart()
    }

    property real entryAngle: 0
    property real flipAngle: flipped ? 180 : 0
    Behavior on flipAngle {
        NumberAnimation { duration: Theme.slow; easing.type: Easing.InOutCubic }
    }

    ParallelAnimation {
        id: arrival
        NumberAnimation { target: body; property: "opacity"; from: 0; to: 1; duration: Theme.medium }
        NumberAnimation { target: body; property: "scale"; from: 0.9; to: 1; duration: Theme.slow; easing.type: Easing.OutBack }
        NumberAnimation { target: root; property: "entryAngle"; from: 32; to: 0; duration: Theme.slow; easing.type: Easing.OutCubic }
        NumberAnimation { target: sheen; property: "at"; from: -0.3; to: 1.3; duration: Theme.slow * 2; easing.type: Easing.InOutQuad }
    }
    Component.onCompleted: arrival.start()

    HoverHandler { id: pointer }
    TapHandler {
        enabled: root.flippable
        onTapped: root.flipped = !root.flipped
    }
    onFlippedChanged: sweep.restart()
    NumberAnimation {
        id: sweep
        target: sheen; property: "at"; from: -0.3; to: 1.3
        duration: Theme.slow * 2; easing.type: Easing.InOutQuad
    }

    Item {
        id: body
        anchors.fill: parent

        readonly property real leanX: pointer.hovered
            ? -(pointer.point.position.y / Math.max(1, root.height) - 0.5) * 12 : 0
        readonly property real leanY: pointer.hovered
            ? (pointer.point.position.x / Math.max(1, root.width) - 0.5) * 16 : 0

        transform: [
            Rotation {
                origin.x: body.width / 2; origin.y: body.height / 2
                axis { x: 1; y: 0; z: 0 }
                angle: body.leanX
                Behavior on angle { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutCubic } }
            },
            Rotation {
                origin.x: body.width / 2; origin.y: body.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: body.leanY + root.entryAngle + root.flipAngle
                Behavior on angle { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            }
        ]

        // -- front -----------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.flipAngle < 90

            Rectangle {
                id: face
                anchors.fill: parent
                radius: 14 * root.unit
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: root.frozen ? "#6b7386" : "#7667f2" }
                    GradientStop { position: 1; color: root.frozen ? "#3c4252" : "#3a2ea3" }
                }
                Behavior on opacity { NumberAnimation { duration: Theme.medium } }
            }
            // Depth: darker toward the lower edge.
            Rectangle {
                anchors.fill: parent
                radius: face.radius
                gradient: Gradient {
                    GradientStop { position: 0; color: "#00000000" }
                    GradientStop { position: 1; color: "#59120c3a" }
                }
            }
            Rectangle {
                id: sheen
                property real at: -0.3
                anchors.fill: parent
                radius: face.radius
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: Math.max(0, Math.min(1, sheen.at - 0.18)); color: "#00ffffff" }
                    GradientStop { position: Math.max(0, Math.min(1, sheen.at)); color: "#2effffff" }
                    GradientStop { position: Math.max(0, Math.min(1, sheen.at + 0.18)); color: "#00ffffff" }
                }
            }
            Rectangle {
                anchors.fill: parent
                radius: face.radius
                color: "transparent"
                border.width: 1
                border.color: "#33ffffff"
            }

            // chip
            Rectangle {
                x: 24 * root.unit
                y: 54 * root.unit
                width: 40 * root.unit
                height: 30 * root.unit
                radius: 6 * root.unit
                gradient: Gradient {
                    GradientStop { position: 0; color: "#ecd9a8" }
                    GradientStop { position: 1; color: "#b89a5e" }
                }
                Rectangle { x: parent.width * 0.34; width: 1; height: parent.height; color: "#66604a20" }
                Rectangle { x: parent.width * 0.66; width: 1; height: parent.height; color: "#66604a20" }
                Rectangle { y: parent.height * 0.5; width: parent.width; height: 1; color: "#66604a20" }
            }

            Text {
                x: 24 * root.unit
                y: 20 * root.unit
                visible: root.frozen
                text: qsTr("Frozen")
                color: "#e6ffffff"
                font.family: Theme.uiFont
                font.pixelSize: 11 * root.unit
                font.weight: Font.DemiBold
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 1.5
            }

            Text {
                x: 24 * root.unit
                y: 104 * root.unit
                text: root.shownNumber
                color: "#f2ffffff"
                font.family: Theme.dataFont
                font.pixelSize: 19 * root.unit
                font.letterSpacing: 1
            }

            Text {
                x: 24 * root.unit
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 20 * root.unit
                width: parent.width - 130 * root.unit
                text: root.holder
                color: "#d9ffffff"
                font.family: Theme.uiFont
                font.pixelSize: 12 * root.unit
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 1.2
                elide: Text.ElideRight
            }

            Text {
                anchors.right: parent.right
                anchors.rightMargin: 22 * root.unit
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 16 * root.unit
                text: root.network === "Visa" ? "VISA" : root.network === "Troy" ? "TROY" : root.network
                color: "#f2ffffff"
                font.family: Theme.uiFont
                font.pixelSize: (root.network === "Mastercard" ? 14 : 20) * root.unit
                font.weight: Font.Bold
                font.italic: root.network === "Visa"
                opacity: root.network.length > 0 ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.medium } }
            }
        }

        // -- back ------------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.flipAngle >= 90
            // Turned with the card, so mirrored back to be readable.
            transform: Rotation {
                origin.x: body.width / 2; origin.y: body.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: 180
            }

            Rectangle {
                anchors.fill: parent
                radius: 14 * root.unit
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "#3a2ea3" }
                    GradientStop { position: 1; color: "#5a4bd6" }
                }
                border.width: 1
                border.color: "#33ffffff"
            }
            Rectangle {
                y: 24 * root.unit
                width: parent.width
                height: 34 * root.unit
                color: "#cc0d0a24"
            }

            Column {
                x: 24 * root.unit
                y: 74 * root.unit
                width: parent.width - 48 * root.unit
                spacing: 7 * root.unit

                Repeater {
                    model: root.details

                    Item {
                        required property var modelData
                        width: parent.width
                        height: 18 * root.unit

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.label
                            color: "#b3ffffff"
                            font.family: Theme.uiFont
                            font.pixelSize: 11 * root.unit
                        }
                        Text {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.value
                            color: "#f2ffffff"
                            font.family: Theme.dataFont
                            font.pixelSize: 12 * root.unit
                        }
                    }
                }
            }
        }
    }
}
