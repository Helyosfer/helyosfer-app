import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    spacing: Theme.gap

    readonly property int colMonth: 60
    readonly property int colMoney: 150

    function calculate() { loan.calculate(amount.text, rate.text, months.text, taxes.checked) }

    // -- Loan calculator ------------------------------------------------
    Card {
        width: parent.width

        Column {
            width: parent.width
            spacing: 16

            Column {
                width: parent.width
                spacing: 3
                Text {
                    text: "Loan calculator"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: "Monthly installment and total cost of a fixed-rate loan."
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
            }

            Flow {
                width: parent.width
                spacing: 12

                Field {
                    id: amount
                    width: 220
                    label: "Loan amount (₺)"
                    placeholder: "0,00"
                    onAccepted: root.calculate()
                }
                Field {
                    id: rate
                    width: 180
                    label: "Monthly interest (%)"
                    placeholder: "3,49"
                    onAccepted: root.calculate()
                }
                Field {
                    id: months
                    width: 130
                    label: "Months"
                    placeholder: "12"
                    input.inputMethodHints: Qt.ImhDigitsOnly
                    onAccepted: root.calculate()
                }
                Item {
                    width: calculateButton.width
                    height: amount.height
                    PrimaryButton {
                        id: calculateButton
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        text: "Calculate"
                        onClicked: root.calculate()
                    }
                }
            }

            Toggle {
                id: taxes
                checked: true
                text: "Include KKDF and BSMV (15 % each on the interest)"
            }

            Notice {
                width: parent.width
                text: loan.message
            }

            Rectangle { width: parent.width; height: 1; color: Theme.lineSoft; visible: loan.hasResult }

            Row {
                width: parent.width
                visible: loan.hasResult

                Repeater {
                    model: [
                        { label: "Monthly installment", value: loan.monthlyText },
                        { label: "Total repaid", value: loan.totalText },
                        { label: "Cost of borrowing", value: loan.costText }
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
                            color: Theme.text
                            font.family: Theme.displayFont
                            font.pixelSize: 24
                            font.weight: Font.Light
                        }
                    }
                }
            }

            Flow {
                width: parent.width
                spacing: 12
                visible: loan.hasResult

                Field {
                    id: debtName
                    width: 260
                    label: "Add this loan to your debts as"
                    placeholder: "Car loan"
                    onAccepted: loan.addToDebts(text)
                }
                Item {
                    width: addButton.width
                    height: debtName.height
                    PrimaryButton {
                        id: addButton
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        quiet: true
                        text: loan.busy ? "Adding…" : "Add to debts"
                        enabled: !loan.busy && debtName.text.trim().length > 0
                        onClicked: loan.addToDebts(debtName.text)
                    }
                }
                Text {
                    height: debtName.height
                    verticalAlignment: Text.AlignBottom
                    bottomPadding: 10
                    text: loan.addedNote
                    color: Theme.up
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }
            }
        }
    }

    // -- Repayment schedule ---------------------------------------------
    Card {
        width: parent.width
        visible: loan.hasResult

        Column {
            width: parent.width

            Text {
                bottomPadding: 10
                text: "Repayment schedule"
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }

            Row {
                height: 26
                Repeater {
                    model: [
                        { label: "Month", width: root.colMonth, left: true },
                        { label: "Installment", width: root.colMoney },
                        { label: "Principal", width: root.colMoney },
                        { label: "Interest and tax", width: root.colMoney },
                        { label: "Remaining", width: root.colMoney }
                    ]
                    Text {
                        required property var modelData
                        width: modelData.width
                        horizontalAlignment: modelData.left ? Text.AlignLeft : Text.AlignRight
                        text: modelData.label
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                    }
                }
            }

            // Only the visible rows exist, however long the loan is.
            ListView {
                width: parent.width
                height: Math.min(contentHeight, 360)
                clip: true
                model: loan.schedule
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}

                delegate: Item {
                    id: line
                    required property var modelData
                    width: ListView.view.width
                    height: 30

                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: [
                                { text: line.modelData.month, width: root.colMonth, left: true },
                                { text: line.modelData.payment, width: root.colMoney },
                                { text: line.modelData.principal, width: root.colMoney },
                                { text: line.modelData.interest, width: root.colMoney },
                                { text: line.modelData.balance, width: root.colMoney }
                            ]
                            Text {
                                required property var modelData
                                width: modelData.width
                                horizontalAlignment: modelData.left ? Text.AlignLeft : Text.AlignRight
                                text: modelData.text
                                color: modelData.left ? Theme.faint : Theme.text
                                font.family: Theme.dataFont
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }
        }
    }
}
