import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    signal addRequested()
    signal moveRequested(var goal, string mode)
    signal autoRequested(var goal)

    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: savings.refresh()

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        PageHeader {
            width: parent.width
            figures: [
                { label: qsTr("Saved in goals"), value: savings.savedText },
                { label: qsTr("Total target"), value: savings.targetText }
            ]
            actionText: qsTr("New goal")
            onAction: root.addRequested()
        }

        Notice {
            width: parent.width
            text: savings.message
        }

        Text {
            width: parent.width
            visible: savings.goals.length === 0
            topPadding: 16
            text: qsTr("No goals yet. Create one to set money aside for something specific.")
            color: Theme.faint
            font.family: Theme.uiFont
            font.pixelSize: 13
        }

        Flow {
            width: parent.width
            spacing: Theme.gap

            Repeater {
                model: savings.goals

                Card {
                    id: card
                    required property var modelData
                    width: page.width >= 900 ? (page.width - Theme.gap) / 2 : page.width

                    Column {
                        width: parent.width
                        spacing: 12

                        Item {
                            width: parent.width
                            height: title.height

                            Text {
                                id: title
                                width: parent.width - badge.width - 12
                                text: card.modelData.name
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            Text {
                                id: badge
                                anchors.right: parent.right
                                anchors.baseline: title.baseline
                                text: card.modelData.done ? qsTr("Reached") : card.modelData.due
                                color: card.modelData.done ? Theme.up : Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }

                        Row {
                            spacing: 8
                            Text {
                                id: figure
                                text: card.modelData.savedText
                                color: Theme.text
                                font.family: Theme.displayFont
                                font.pixelSize: 28
                                font.weight: Font.Light
                            }
                            Text {
                                anchors.baseline: figure.baseline
                                text: qsTr("of %1").arg(card.modelData.targetText) + "  ·  " + card.modelData.percent
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 6
                            radius: 3
                            color: Theme.lineSoft
                            Rectangle {
                                width: parent.width * card.modelData.progress
                                height: parent.height
                                radius: 3
                                color: card.modelData.done ? Theme.up : Theme.accent
                            }
                        }

                        Text {
                            width: parent.width
                            text: card.modelData.done ? qsTr("Nothing left to save.")
                                : qsTr("%1 to go").arg(card.modelData.remainingText)
                                  + (card.modelData.pace.length > 0 ? "  ·  " + card.modelData.pace : "")
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            width: parent.width
                            visible: card.modelData.auto
                            text: qsTr("Automatic: %1").arg(card.modelData.autoText)
                            color: Theme.accent
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }

                        Flow {
                            width: parent.width
                            spacing: 10

                            PrimaryButton {
                                compact: true; quiet: true
                                visible: !card.modelData.done
                                text: qsTr("Add money")
                                onClicked: root.moveRequested(card.modelData, "deposit")
                            }
                            PrimaryButton {
                                compact: true; quiet: true
                                visible: !card.modelData.done
                                text: card.modelData.auto ? qsTr("Change automatic saving")
                                                          : qsTr("Save automatically")
                                onClicked: root.autoRequested(card.modelData)
                            }
                            PrimaryButton {
                                compact: true; quiet: true
                                enabled: card.modelData.hasMoney
                                text: qsTr("Take back")
                                onClicked: root.moveRequested(card.modelData, "withdraw")
                            }
                            PrimaryButton {
                                compact: true; quiet: true; danger: true
                                text: qsTr("Delete")
                                onClicked: root.moveRequested(card.modelData, "delete")
                            }
                        }
                    }
                }
            }
        }
    }
}
