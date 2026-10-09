import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    spacing: Theme.gap

    Component.onCompleted: insights.refresh()

    Notice {
        width: parent.width
        text: insights.message
    }

    Row {
        width: parent.width
        spacing: Theme.gap

        // -- Health score ---------------------------------------------------
        Card {
            id: healthCard
            width: (parent.width - Theme.gap) * 0.6

            Column {
                width: parent.width
                spacing: 12

                Text {
                    text: qsTr("Financial health")
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Row {
                    visible: insights.healthReady
                    spacing: 10
                    Text {
                        id: scoreText
                        text: insights.score
                        color: Theme.text
                        font.family: Theme.displayFont
                        font.pixelSize: 44
                        font.weight: Font.Light
                    }
                    Text {
                        anchors.baseline: scoreText.baseline
                        text: qsTr("out of 100") + "  ·  " + insights.scoreLabel
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 13
                    }
                }

                Rectangle {
                    visible: insights.healthReady
                    width: parent.width
                    height: 6
                    radius: 3
                    color: Theme.lineSoft
                    Rectangle {
                        width: parent.width * insights.scoreRatio
                        height: parent.height
                        radius: 3
                        color: insights.scoreRatio >= 0.6 ? Theme.up
                            : insights.scoreRatio >= 0.4 ? Theme.accent : Theme.warn
                    }
                }

                Column {
                    width: parent.width
                    visible: insights.healthReady

                    Repeater {
                        model: insights.healthRows
                        Item {
                            id: part
                            required property var modelData
                            width: parent.width
                            height: 38

                            Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: part.modelData.label + "  ·  " + part.modelData.weight
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.right: parent.right
                                text: part.modelData.value + "   " + part.modelData.points
                                color: Theme.text
                                font.family: Theme.dataFont
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: insights.healthNote
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
        }

        // -- Forecast -------------------------------------------------------
        Card {
            width: parent.width - healthCard.width - Theme.gap

            Column {
                width: parent.width
                spacing: 10

                Text {
                    text: qsTr("Month-end forecast")
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    visible: insights.forecastReady
                    text: insights.forecastBalance
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 28
                    font.weight: Font.Light
                }
                Text {
                    visible: insights.forecastReady
                    text: insights.forecastChange
                    color: Theme.direction(insights.forecastDirection)
                    font.family: Theme.dataFont
                    font.pixelSize: 12
                }
                Text {
                    width: parent.width
                    text: insights.forecastNote
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    // -- Unusual spending ---------------------------------------------------
    Card {
        width: parent.width

        Column {
            width: parent.width

            Text {
                bottomPadding: 10
                text: qsTr("Unusual spending")
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                visible: insights.anomalies.length === 0
                topPadding: 6
                text: qsTr("Nothing stands out from your usual spending in the last 90 days.")
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 13
            }

            Repeater {
                model: insights.anomalies
                Item {
                    id: line
                    required property var modelData
                    width: parent.width
                    height: 52

                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.right: sum.left
                        anchors.rightMargin: 16
                        spacing: 2
                        Text {
                            width: parent.width
                            text: line.modelData.title + "  ·  " + line.modelData.category
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            text: line.modelData.date + "  ·  " + line.modelData.note
                            color: Theme.warn
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                    }
                    Text {
                        id: sum
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.right: dismiss.left
                        anchors.rightMargin: 20
                        text: line.modelData.amount
                        color: Theme.text
                        font.family: Theme.dataFont
                        font.pixelSize: 13
                    }
                    PrimaryButton {
                        id: dismiss
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true; quiet: true
                        text: qsTr("This is fine")
                        enabled: !insights.busy
                        onClicked: insights.dismissAnomaly(line.modelData.id)
                    }
                }
            }
        }
    }

    // -- Possible subscriptions ---------------------------------------------
    Card {
        width: parent.width

        Column {
            width: parent.width

            Text {
                bottomPadding: 10
                text: qsTr("Payments that look recurring")
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                visible: insights.candidates.length === 0
                topPadding: 6
                text: qsTr("No repeating payments were found that you are not already tracking.")
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 13
            }

            Repeater {
                model: insights.candidates
                Item {
                    id: row
                    required property var modelData
                    width: parent.width
                    height: 52

                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.right: cost.left
                        anchors.rightMargin: 16
                        spacing: 2
                        Text {
                            width: parent.width
                            text: row.modelData.name + "  ·  " + row.modelData.category
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            text: row.modelData.frequency + "  ·  " + row.modelData.seen
                                + "  ·  " + row.modelData.monthly
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                    }
                    Text {
                        id: cost
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.right: actions.left
                        anchors.rightMargin: 20
                        text: row.modelData.amount
                        color: Theme.text
                        font.family: Theme.dataFont
                        font.pixelSize: 13
                    }
                    Row {
                        id: actions
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        PrimaryButton {
                            compact: true; quiet: true
                            visible: row.modelData.canTrack
                            enabled: !insights.busy
                            text: qsTr("Track")
                            onClicked: insights.trackCandidate(
                                row.modelData.key,
                                accounts.options.length > 0 ? accounts.options[0].key : -1)
                        }
                        PrimaryButton {
                            compact: true; quiet: true
                            enabled: !insights.busy
                            text: qsTr("Ignore")
                            onClicked: insights.dismissCandidate(row.modelData.key)
                        }
                    }
                }
            }
        }
    }
}
