import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    signal addRequested()
    signal payRequested(var debt, bool payOff)
    signal autoPayRequested(var debt)
    signal rescheduleRequested(var item)

    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: debts.refresh()

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        PageHeader {
            width: parent.width
            figures: [
                { label: qsTr("Total owed"), value: debts.totalText },
                { label: qsTr("Due each month"), value: debts.monthlyText }
            ]
            actionText: qsTr("Add debt")
            onAction: root.addRequested()
        }

        Notice {
            width: parent.width
            text: debts.message
        }

        // -- Debts ----------------------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width

                Text {
                    bottomPadding: 10
                    text: qsTr("Debts")
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Text {
                    visible: debts.debts.length === 0
                    topPadding: 6
                    text: qsTr("No active debts. Loans and installment debts you add appear here.")
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: debts.debts

                    Item {
                        id: row
                        required property var modelData
                        width: parent.width
                        height: 92

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                        Column {
                            anchors.left: parent.left
                            anchors.right: actions.left
                            anchors.rightMargin: 24
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            Item {
                                width: parent.width
                                height: nameLabel.height
                                Text {
                                    id: nameLabel
                                    text: row.modelData.name
                                    color: Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    width: parent.width - owed.width - 16
                                }
                                Text {
                                    id: owed
                                    anchors.right: parent.right
                                    anchors.baseline: nameLabel.baseline
                                    text: row.modelData.remainingText
                                    color: Theme.text
                                    font.family: Theme.dataFont
                                    font.pixelSize: 14
                                }
                            }

                            Rectangle {
                                width: parent.width
                                height: 6
                                radius: 3
                                color: Theme.lineSoft
                                Rectangle {
                                    width: parent.width * row.modelData.progress
                                    Behavior on width { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                                    height: parent.height
                                    radius: 3
                                    color: Theme.accent
                                }
                            }

                            Text {
                                text: row.modelData.progressText + "  ·  " + qsTr("%1 a month").arg(row.modelData.monthlyText)
                                    + (!row.modelData.autoPay ? ""
                                       : "  ·  " + (row.modelData.autoPayAccount.length > 0
                                           ? qsTr("automatic on day %1 from %2").arg(row.modelData.autoPayDay).arg(row.modelData.autoPayAccount)
                                           : qsTr("automatic on day %1").arg(row.modelData.autoPayDay)))
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }

                        Row {
                            id: actions
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            PrimaryButton {
                                compact: true; quiet: true
                                text: row.modelData.autoPay ? qsTr("Automatic: on") : qsTr("Automatic: off")
                                onClicked: row.modelData.autoPay
                                    ? debts.setAutoPay(row.modelData.id, false, "", -1)
                                    : root.autoPayRequested(row.modelData)
                            }
                            PrimaryButton {
                                compact: true; quiet: true
                                text: qsTr("Pay")
                                onClicked: root.payRequested(row.modelData, false)
                            }
                            PrimaryButton {
                                compact: true; quiet: true
                                text: qsTr("Pay off")
                                onClicked: root.payRequested(row.modelData, true)
                            }
                        }
                    }
                }
            }
        }

        // -- Pending transactions -------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width

                Text {
                    bottomPadding: 10
                    text: qsTr("Pending transactions")
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Text {
                    visible: debts.pending.length === 0
                    topPadding: 6
                    text: qsTr("Nothing is waiting. Transactions saved with a future date appear here until that day.")
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: debts.pending

                    Item {
                        id: line
                        required property var modelData
                        width: parent.width
                        height: 46

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                        Text {
                            id: due
                            anchors.verticalCenter: parent.verticalCenter
                            width: 170
                            text: line.modelData.due
                            color: Theme.muted
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: due.right
                            anchors.right: sum.left
                            anchors.rightMargin: 16
                            text: line.modelData.title
                                + (line.modelData.account.length > 0 ? "  ·  " + line.modelData.account : "")
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: sum
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: lineActions.left
                            anchors.rightMargin: 20
                            text: line.modelData.amount
                            color: line.modelData.income ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 13
                        }
                        Row {
                            id: lineActions
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8
                            PrimaryButton {
                                compact: true; quiet: true
                                text: qsTr("Reschedule")
                                onClicked: root.rescheduleRequested(line.modelData)
                            }
                            PrimaryButton {
                                compact: true; quiet: true; danger: true
                                text: qsTr("Cancel")
                                onClicked: debts.cancelPending(line.modelData.id)
                            }
                        }
                    }
                }
            }
        }
    }
}
