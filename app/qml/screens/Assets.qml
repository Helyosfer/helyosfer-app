import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    signal addRequested()
    signal sellRequested(var holding)

    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: assets.refresh()

    // Column widths shared by the header and every row.
    readonly property int colQuantity: 110
    readonly property int colMoney: 130
    readonly property int colPnl: 190
    readonly property int colAction: 70

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        PageHeader {
            width: parent.width
            figures: [
                { label: "Portfolio value", value: assets.valueText },
                { label: "Cost", value: assets.costText }
            ]
            actionText: "Add asset"
            onAction: root.addRequested()
        }

        Item {
            width: parent.width
            height: refresh.height

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: assets.pnlText.length > 0 ? "Profit or loss  " + assets.pnlText : ""
                color: Theme.direction(assets.pnlDirection)
                font.family: Theme.dataFont
                font.pixelSize: 13
            }
            Row {
                anchors.right: parent.right
                spacing: 12
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: assets.pricing || assets.unpricedCount > 0
                    text: assets.pricing ? "Updating prices…"
                        : assets.unpricedCount + (assets.unpricedCount === 1 ? " holding has" : " holdings have")
                          + " no current price and are counted at cost"
                    color: assets.pricing ? Theme.muted : Theme.warn
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
                PrimaryButton {
                    id: refresh
                    compact: true; quiet: true
                    text: "Refresh prices"
                    enabled: !assets.pricing && assets.holdings.length > 0
                    onClicked: assets.refreshPrices()
                }
            }
        }

        Notice {
            width: parent.width
            text: assets.message
        }

        // -- Holdings -------------------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width

                Item {
                    width: parent.width
                    height: 28

                    Text { text: "Holding"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
                    Row {
                        anchors.right: parent.right
                        Repeater {
                            model: [
                                { label: "Quantity", width: root.colQuantity },
                                { label: "Unit cost", width: root.colMoney },
                                { label: "Price", width: root.colMoney },
                                { label: "Value", width: root.colMoney },
                                { label: "Profit or loss", width: root.colPnl },
                                { label: "", width: root.colAction }
                            ]
                            Text {
                                required property var modelData
                                width: modelData.width
                                horizontalAlignment: Text.AlignRight
                                text: modelData.label
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                Text {
                    visible: assets.holdings.length === 0
                    topPadding: 10
                    text: "No assets yet. Add shares, gold, currency or crypto to follow their value."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: assets.holdings

                    Item {
                        id: row
                        required property var modelData
                        width: parent.width
                        height: 54

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                        Column {
                            anchors.left: parent.left
                            anchors.right: cells.left
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text {
                                width: parent.width
                                text: row.modelData.name
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            Text {
                                text: row.modelData.code + "  ·  " + row.modelData.kind
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }

                        Row {
                            id: cells
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter

                            Repeater {
                                model: [
                                    { text: row.modelData.quantityText, width: root.colQuantity, tone: 0 },
                                    { text: row.modelData.costText, width: root.colMoney, tone: 0 },
                                    { text: row.modelData.priceText, width: root.colMoney, tone: 0 },
                                    { text: row.modelData.valueText, width: root.colMoney, tone: 0 },
                                    { text: row.modelData.pnlText, width: root.colPnl,
                                      tone: row.modelData.priced ? (row.modelData.direction === 0 ? 3 : row.modelData.direction) : 2 }
                                ]
                                Text {
                                    required property var modelData
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: modelData.width
                                    horizontalAlignment: Text.AlignRight
                                    text: modelData.text
                                    color: modelData.tone === 1 ? Theme.up
                                        : modelData.tone === -1 ? Theme.down
                                        : modelData.tone === 2 ? Theme.faint
                                        : modelData.tone === 3 ? Theme.muted : Theme.text
                                    font.family: Theme.dataFont
                                    font.pixelSize: 13
                                }
                            }
                            Item {
                                width: root.colAction
                                height: sell.height
                                PrimaryButton {
                                    id: sell
                                    anchors.right: parent.right
                                    compact: true; quiet: true
                                    text: "Sell"
                                    onClicked: root.sellRequested(row.modelData)
                                }
                            }
                        }
                    }
                }
            }
        }

        // -- History --------------------------------------------------------
        Card {
            width: parent.width
            visible: assets.history.length > 0

            Column {
                width: parent.width

                Text {
                    bottomPadding: 10
                    text: "Purchases and sales"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Repeater {
                    model: assets.history
                    Item {
                        id: line
                        required property var modelData
                        width: parent.width
                        height: 38

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        Text {
                            id: when
                            anchors.verticalCenter: parent.verticalCenter
                            width: 64
                            text: line.modelData.date
                            color: Theme.faint
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: when.right
                            anchors.right: sum.left
                            anchors.rightMargin: 16
                            text: line.modelData.title
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: sum
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            text: line.modelData.amount
                            color: line.modelData.income ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }
}
