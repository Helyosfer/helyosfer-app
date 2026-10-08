import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    signal addAccountRequested()
    signal addTransactionRequested(int accountId)
    signal payDebtRequested(var account)
    signal deleteRequested(var account)

    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: accounts.refresh()

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        // -- Header ---------------------------------------------------------
        Item {
            width: parent.width
            height: totals.height

            Row {
                id: totals
                spacing: 40

                Repeater {
                    model: [
                        { label: "Cash and checking", value: accounts.cashText },
                        { label: "Card debt", value: accounts.debtText }
                    ]
                    Column {
                        required property var modelData
                        spacing: 2
                        Text {
                            text: modelData.label
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                        Text {
                            text: modelData.value
                            color: Theme.text
                            font.family: Theme.displayFont
                            font.pixelSize: 26
                            font.weight: Font.Light
                        }
                    }
                }
            }

            PrimaryButton {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "Add account"
                onClicked: root.addAccountRequested()
            }
        }

        Text {
            width: parent.width
            visible: accounts.accounts.length === 0
            topPadding: 24
            text: "No accounts yet. Add the account you use most to get started."
            color: Theme.faint
            font.family: Theme.uiFont
            font.pixelSize: 13
        }

        // -- Account cards --------------------------------------------------
        Flow {
            width: parent.width
            spacing: Theme.gap

            Repeater {
                model: accounts.accounts

                Card {
                    id: card
                    required property var modelData
                    readonly property bool credit: modelData.kind === "credit_card"
                    width: page.width >= 900 ? (page.width - Theme.gap) / 2 : page.width

                    Column {
                        width: parent.width
                        spacing: 14

                        // name, type and card digits
                        Item {
                            width: parent.width
                            height: 38

                            Column {
                                spacing: 2
                                Text {
                                    text: card.modelData.name
                                    color: Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: card.modelData.typeLabel
                                        + (card.modelData.frozen ? "  ·  Frozen" : "")
                                    color: card.modelData.frozen ? Theme.warn : Theme.muted
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                }
                            }
                            Text {
                                anchors.right: parent.right
                                visible: card.modelData.lastFour.length > 0
                                text: (card.modelData.network.length > 0 ? card.modelData.network + "  " : "")
                                    + "•••• " + card.modelData.lastFour
                                color: Theme.muted
                                font.family: Theme.dataFont
                                font.pixelSize: 12
                            }
                        }

                        // headline figure
                        Column {
                            width: parent.width
                            spacing: 8

                            Row {
                                spacing: 8
                                Text {
                                    id: figure
                                    text: card.credit ? card.modelData.debtText : card.modelData.balanceText
                                    color: Theme.text
                                    font.family: Theme.displayFont
                                    font.pixelSize: 28
                                    font.weight: Font.Light
                                }
                                Text {
                                    anchors.baseline: figure.baseline
                                    visible: card.credit
                                    text: "owed of " + card.modelData.limitText
                                    color: Theme.muted
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                }
                            }

                            Rectangle {
                                visible: card.credit
                                width: parent.width
                                height: 6
                                radius: 3
                                color: Theme.lineSoft
                                Rectangle {
                                    width: parent.width * card.modelData.usage
                                    height: parent.height
                                    radius: 3
                                    color: card.modelData.usage > 0.85 ? Theme.warn : Theme.accent
                                }
                            }

                            Text {
                                visible: card.credit
                                text: card.modelData.availableText + " available"
                                    + (card.modelData.statementDay > 0
                                       ? "  ·  statement on day " + card.modelData.statementDay : "")
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }

                        // recent activity
                        Column {
                            width: parent.width

                            Text {
                                visible: card.modelData.recent.length === 0
                                text: "No transactions yet."
                                color: Theme.faint
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }

                            Repeater {
                                model: card.modelData.recent
                                Item {
                                    id: line
                                    required property var modelData
                                    width: parent.width
                                    height: 30

                                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                                    Text {
                                        id: when
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 60
                                        text: line.modelData.date
                                        color: Theme.faint
                                        font.family: Theme.dataFont
                                        font.pixelSize: 11
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: when.right
                                        anchors.right: sum.left
                                        anchors.rightMargin: 12
                                        text: line.modelData.title
                                        color: Theme.text
                                        font.family: Theme.uiFont
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        id: sum
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.right: parent.right
                                        text: line.modelData.amount
                                        color: line.modelData.income ? Theme.up : Theme.text
                                        font.family: Theme.dataFont
                                        font.pixelSize: 12
                                    }
                                }
                            }
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                        // controls
                        Flow {
                            width: parent.width
                            spacing: 20

                            Toggle {
                                text: "Freeze"
                                checked: card.modelData.frozen
                                onToggled: accounts.setFrozen(card.modelData.id, checked)
                            }
                            Toggle {
                                visible: card.credit || card.modelData.lastFour.length > 0
                                text: "Online payments"
                                checked: card.modelData.onlinePayments
                                onToggled: accounts.setOnlinePayments(card.modelData.id, checked)
                            }
                        }

                        Flow {
                            width: parent.width
                            spacing: 10

                            PrimaryButton {
                                quiet: true
                                text: "Add transaction"
                                enabled: !card.modelData.frozen
                                onClicked: root.addTransactionRequested(card.modelData.id)
                            }
                            PrimaryButton {
                                quiet: true
                                visible: card.credit
                                enabled: card.modelData.hasDebt
                                text: "Pay debt"
                                onClicked: root.payDebtRequested(card.modelData)
                            }
                            PrimaryButton {
                                quiet: true
                                danger: true
                                visible: card.credit
                                text: "Delete"
                                onClicked: root.deleteRequested(card.modelData)
                            }
                        }
                    }
                }
            }
        }
    }
}
