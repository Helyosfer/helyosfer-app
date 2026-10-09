import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    spacing: Theme.gap

    function run() {
        scenario.run(income.text, expense.text, oneTime.text,
                     horizon.currentKey === undefined ? "90" : horizon.currentKey)
    }

    Component.onCompleted: { horizon.select("90"); run() }

    Card {
        width: parent.width

        Column {
            width: parent.width
            spacing: 16

            Column {
                width: parent.width
                spacing: 3
                Text {
                    text: "What if"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: "Compare where your balance is heading with a change you are considering. Nothing here is saved."
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            Flow {
                width: parent.width
                spacing: 12

                Field {
                    id: income
                    width: 170
                    label: "Income change (%)"
                    placeholder: "0"
                    onAccepted: root.run()
                }
                Field {
                    id: expense
                    width: 170
                    label: "Spending change (%)"
                    placeholder: "0"
                    onAccepted: root.run()
                }
                Field {
                    id: oneTime
                    width: 220
                    label: "One-time amount (₺, minus to spend)"
                    placeholder: "0"
                    money: true
                    signed: true
                    onAccepted: root.run()
                }
                Choice {
                    id: horizon
                    width: 150
                    label: "Over"
                    model: scenario.horizons
                }
                Item {
                    width: runButton.width
                    height: income.height
                    PrimaryButton {
                        id: runButton
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        text: scenario.busy ? "Working…" : "Compare"
                        enabled: !scenario.busy
                        onClicked: root.run()
                    }
                }
            }

            Notice {
                width: parent.width
                text: scenario.message
            }
        }
    }

    Card {
        width: parent.width
        visible: scenario.hasResult

        Column {
            width: parent.width
            spacing: 14

            Row {
                width: parent.width

                Repeater {
                    model: [
                        { label: "As things are", value: scenario.baseText, tone: 0 },
                        { label: "With the change", value: scenario.scenarioText, tone: 0 },
                        { label: "Difference", value: scenario.differenceText, tone: scenario.differenceDirection }
                    ]
                    Column {
                        required property var modelData
                        width: parent.width / 3
                        spacing: 2
                        Text {
                            text: modelData.label
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                        Text {
                            text: modelData.value
                            color: modelData.tone === 0 ? Theme.text : Theme.direction(modelData.tone)
                            font.family: Theme.displayFont
                            font.pixelSize: 24
                            font.weight: Font.Light
                        }
                    }
                }
            }

            LineChart {
                width: parent.width
                height: 240
                values: scenario.scenarioSeries
                compare: scenario.baseSeries
                labels: scenario.labels
            }

            Text {
                width: parent.width
                text: "The brighter line is the change; the fainter one is how things are now.  " + scenario.note
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                visible: scenario.goesNegative
                text: "With this change the balance drops below zero at some point in the period."
                color: Theme.warn
                font.family: Theme.uiFont
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
        }
    }
}
