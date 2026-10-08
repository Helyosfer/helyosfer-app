import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    signal addRequested()
    signal amountRequested(var item)
    signal stopRequested(var item)

    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: recurring.refresh()

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        PageHeader {
            width: parent.width
            figures: [
                { label: "Recurring cost per month", value: recurring.monthlyText },
                { label: "Active", value: recurring.items.length.toString() }
            ]
            actionText: "Add recurring payment"
            onAction: root.addRequested()
        }

        Notice {
            width: parent.width
            text: recurring.message
        }

        Card {
            width: parent.width

            Column {
                width: parent.width

                Text {
                    bottomPadding: 10
                    text: "Subscriptions and recurring payments"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Text {
                    width: parent.width
                    visible: recurring.items.length === 0
                    topPadding: 6
                    text: "Nothing recurring yet. Subscriptions are also picked up automatically from card spending."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }

                Repeater {
                    model: recurring.items

                    Item {
                        id: row
                        required property var modelData
                        width: parent.width
                        height: 64

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                        Column {
                            anchors.left: parent.left
                            anchors.right: sum.left
                            anchors.rightMargin: 16
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3

                            Text {
                                width: parent.width
                                text: row.modelData.name
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            Row {
                                spacing: 0
                                Text {
                                    text: row.modelData.due
                                    color: row.modelData.overdue ? Theme.warn : Theme.muted
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                }
                                Text {
                                    text: "  ·  " + row.modelData.frequency
                                        + (row.modelData.account.length > 0 ? "  ·  " + row.modelData.account : "")
                                        + (row.modelData.automatic ? "  ·  automatic" : "  ·  manual")
                                    color: Theme.muted
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                }
                            }
                        }

                        Text {
                            id: sum
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: actions.left
                            anchors.rightMargin: 20
                            text: row.modelData.amountText
                            color: row.modelData.income ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 14
                        }

                        Row {
                            id: actions
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            PrimaryButton {
                                compact: true; quiet: true
                                enabled: row.modelData.valid && !recurring.busy
                                text: row.modelData.income ? "Receive now" : "Pay now"
                                onClicked: recurring.payNow(row.modelData.id)
                            }
                            PrimaryButton {
                                compact: true; quiet: true
                                enabled: !recurring.busy
                                text: "Skip next"
                                onClicked: recurring.skipNext(row.modelData.id)
                            }
                            PrimaryButton {
                                compact: true; quiet: true
                                text: "Change amount"
                                onClicked: root.amountRequested(row.modelData)
                            }
                            PrimaryButton {
                                compact: true; quiet: true; danger: true
                                text: "Stop"
                                onClicked: root.stopRequested(row.modelData)
                            }
                        }
                    }
                }
            }
        }
    }
}
