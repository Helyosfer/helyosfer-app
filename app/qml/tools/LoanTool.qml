import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import ".."
import "../components"

Column {
    id: root
    spacing: Theme.gap

    readonly property int colMonth: 60
    readonly property int colMoney: 138

    function calculate() {
        loan.calculate(amount.text, rate.text, months.text, taxes.checked, detailed.checked,
                       kind.currentKey === undefined ? "" : kind.currentKey)
    }

    Component.onCompleted: kind.select("consumer")

    Card {
        width: parent.width

        Column {
            width: parent.width
            spacing: 16

            Column {
                width: parent.width
                spacing: 3
                Text {
                    text: "Loan"
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

            Flow {
                width: parent.width
                spacing: 24

                Toggle {
                    id: taxes
                    checked: true
                    text: "Include KKDF and BSMV (15 % each on the interest)"
                }
                Toggle {
                    id: detailed
                    text: "Include bank fees and my own charges"
                }
            }

            // -- Detailed mode ------------------------------------------------
            Column {
                width: parent.width
                spacing: 12
                visible: detailed.checked

                Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                Choice {
                    id: kind
                    width: 300
                    label: "Kind of loan"
                    model: loan.kinds
                }

                Text {
                    width: parent.width
                    text: "An allocation fee (0,5 % plus tax) and life insurance (about 0,8 %) are deducted up front. Add anything else the bank charges below."
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }

                Flow {
                    width: parent.width
                    spacing: 12

                    Field {
                        id: chargeName
                        width: 220
                        label: "Charge"
                        placeholder: "Appraisal fee"
                    }
                    Field {
                        id: chargeAmount
                        width: 150
                        label: "Amount (₺)"
                        placeholder: "0,00"
                    }
                    Item {
                        width: spreadToggle.width
                        height: chargeName.height
                        Toggle {
                            id: spreadToggle
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 10
                            text: "Spread over months"
                        }
                    }
                    Field {
                        id: chargeMonths
                        visible: spreadToggle.checked
                        width: 110
                        label: "Months"
                        placeholder: "12"
                        input.inputMethodHints: Qt.ImhDigitsOnly
                    }
                    Item {
                        width: addCharge.width
                        height: chargeName.height
                        PrimaryButton {
                            id: addCharge
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 2
                            quiet: true
                            text: "Add charge"
                            onClicked: {
                                var before = loan.charges.length
                                loan.addCharge(chargeName.text, chargeAmount.text,
                                               spreadToggle.checked, chargeMonths.text)
                                if (loan.charges.length > before) {
                                    chargeName.text = ""
                                    chargeAmount.text = ""
                                }
                            }
                        }
                    }
                }

                Column {
                    width: parent.width
                    Repeater {
                        model: loan.charges
                        Item {
                            id: chargeRow
                            required property var modelData
                            required property int index
                            width: parent.width
                            height: 38

                            Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: chargeRow.modelData.name + "  ·  " + chargeRow.modelData.detail
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.right: removeCharge.left
                                anchors.rightMargin: 16
                                text: chargeRow.modelData.amount
                                color: Theme.text
                                font.family: Theme.dataFont
                                font.pixelSize: 13
                            }
                            PrimaryButton {
                                id: removeCharge
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                compact: true; quiet: true; danger: true
                                text: "Remove"
                                onClicked: loan.removeCharge(chargeRow.index)
                            }
                        }
                    }
                }
            }

            Notice {
                width: parent.width
                text: loan.message
            }

            Rectangle { width: parent.width; height: 1; color: Theme.lineSoft; visible: loan.hasResult }

            Figures {
                width: parent.width
                visible: loan.hasResult
                rows: loan.hasDeductions
                    ? [
                        { label: "Monthly installment", value: loan.monthlyText, tone: 0 },
                        { label: "Total repaid", value: loan.totalText, tone: 0 },
                        { label: "Cost with all charges", value: loan.costText, tone: 0 },
                        { label: "Cash you receive", value: loan.netCashText, tone: 0 }
                      ]
                    : [
                        { label: "Monthly installment", value: loan.monthlyText, tone: 0 },
                        { label: "Total repaid", value: loan.totalText, tone: 0 },
                        { label: "Cost of borrowing", value: loan.costText, tone: 0 }
                      ]
            }

            Column {
                width: parent.width
                visible: loan.hasDeductions

                Text {
                    bottomPadding: 6
                    text: "Deducted up front"
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
                Repeater {
                    model: loan.deductions
                    Item {
                        id: deduction
                        required property var modelData
                        width: parent.width
                        height: 30
                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: deduction.modelData.label
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            text: deduction.modelData.value
                            color: Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 12
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
                    width: actions.width
                    height: debtName.height
                    Row {
                        id: actions
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        spacing: 10
                        PrimaryButton {
                            quiet: true
                            text: "Add to debts"
                            enabled: !loan.busy && debtName.text.trim().length > 0
                            onClicked: loan.addToDebts(debtName.text)
                        }
                        PrimaryButton {
                            quiet: true
                            text: "Save schedule as PDF"
                            enabled: !loan.busy
                            onClicked: pdfFile.open()
                        }
                    }
                }
                Text {
                    height: debtName.height
                    verticalAlignment: Text.AlignBottom
                    bottomPadding: 10
                    text: loan.note
                    color: Theme.up
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }
            }
        }
    }

    // -- Repayment schedule -------------------------------------------------
    Card {
        width: parent.width
        visible: loan.hasResult

        Column {
            id: table
            width: parent.width

            readonly property var columns: loan.hasExtras
                ? [
                    { label: "Month", key: "month", width: root.colMonth, left: true },
                    { label: "Installment", key: "payment", width: root.colMoney },
                    { label: "Extra charges", key: "extra", width: root.colMoney },
                    { label: "Total", key: "total", width: root.colMoney },
                    { label: "Principal", key: "principal", width: root.colMoney },
                    { label: "Interest and tax", key: "interest", width: root.colMoney },
                    { label: "Remaining", key: "balance", width: root.colMoney }
                  ]
                : [
                    { label: "Month", key: "month", width: root.colMonth, left: true },
                    { label: "Installment", key: "payment", width: root.colMoney },
                    { label: "Principal", key: "principal", width: root.colMoney },
                    { label: "Interest and tax", key: "interest", width: root.colMoney },
                    { label: "Remaining", key: "balance", width: root.colMoney }
                  ]

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
                    model: table.columns
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
                            model: table.columns
                            Text {
                                required property var modelData
                                width: modelData.width
                                horizontalAlignment: modelData.left ? Text.AlignLeft : Text.AlignRight
                                text: line.modelData[modelData.key]
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

    FileDialog {
        id: pdfFile
        title: "Save repayment schedule"
        fileMode: FileDialog.SaveFile
        nameFilters: ["PDF (*.pdf)"]
        defaultSuffix: "pdf"
        onAccepted: loan.exportPdf(selectedFile)
    }
}
