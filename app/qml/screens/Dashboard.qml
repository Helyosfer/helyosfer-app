import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: dashboard.refresh()

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        Text {
            width: parent.width
            visible: dashboard.error.length > 0
            text: dashboard.error
            color: Theme.down
            font.family: Theme.uiFont
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }

        // -- Balance stage -------------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width
                spacing: 14

                Item {
                    width: parent.width
                    height: headline.height

                    Column {
                        id: headline
                        spacing: 4

                        Text {
                            text: "Total balance"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                        Row {
                            spacing: 2
                            Text {
                                id: whole
                                text: dashboard.balanceWhole
                                color: Theme.text
                                font.family: Theme.displayFont
                                font.pixelSize: 48
                                font.weight: Font.Light
                            }
                            Text {
                                anchors.baseline: whole.baseline
                                text: dashboard.balanceFraction
                                color: Theme.muted
                                font.family: Theme.displayFont
                                font.pixelSize: 22
                                font.weight: Font.Light
                            }
                        }
                        Text {
                            text: dashboard.changeText
                            color: Theme.direction(dashboard.changeDirection)
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                    }

                    Segmented {
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        model: dashboard.periods
                        current: dashboard.period
                        onChosen: function (key) { dashboard.setPeriod(key) }
                    }
                }

                LineChart {
                    width: parent.width
                    height: 220
                    values: dashboard.series
                    labels: dashboard.seriesLabels
                }

                Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                Row {
                    width: parent.width

                    Repeater {
                        model: [
                            { label: "Income", value: dashboard.incomeText, tone: 0 },
                            { label: "Spending", value: dashboard.expenseText, tone: 0 },
                            { label: "Net", value: dashboard.netText, tone: dashboard.netDirection }
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
                                font.family: Theme.uiFont
                                font.pixelSize: 17
                                font.weight: Font.Medium
                            }
                        }
                    }
                }
            }
        }

        // -- Recent transactions -------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width
                spacing: 0

                Text {
                    bottomPadding: 10
                    text: "Recent transactions"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Text {
                    visible: dashboard.recent.length === 0
                    topPadding: 6
                    text: "Transactions you add will appear here."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: dashboard.recent

                    Item {
                        id: row
                        required property var modelData
                        width: parent.width
                        height: 40

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                        Text {
                            id: dateLabel
                            anchors.verticalCenter: parent.verticalCenter
                            width: 64
                            text: row.modelData.date
                            color: Theme.faint
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: dateLabel.right
                            anchors.right: categoryLabel.left
                            anchors.rightMargin: 16
                            text: row.modelData.title
                            color: row.modelData.readable ? Theme.text : Theme.down
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: categoryLabel
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: amountLabel.left
                            anchors.rightMargin: 24
                            width: 180
                            text: row.modelData.category
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: amountLabel
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            width: 140
                            horizontalAlignment: Text.AlignRight
                            text: row.modelData.amount
                            color: row.modelData.income ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }
}
