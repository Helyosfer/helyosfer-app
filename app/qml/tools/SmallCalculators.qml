import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// The four short calculators. `which` selects one; only that one exists.
Column {
    id: root
    property string which: "interest"
    spacing: Theme.gap

    // A titled card with a form on top and results below.
    component CalculatorCard: Card {
        property string heading: ""
        property string summary: ""
        default property alias body: inner.data
        width: parent.width

        Column {
            id: inner
            width: parent.width
            spacing: 16

            Column {
                width: parent.width
                spacing: 3
                Text {
                    text: heading
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: summary
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    component RunButton: Item {
        property alias text: button.text
        property int fieldHeight: 62
        signal clicked()
        width: button.width
        height: fieldHeight
        PrimaryButton {
            id: button
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
            text: "Calculate"
            onClicked: parent.clicked()
        }
    }

    Loader {
        width: parent.width
        sourceComponent: root.which === "interest" ? interestCalculator
            : root.which === "growth" ? growthCalculator
            : root.which === "goal" ? goalCalculator : plainCalculator
    }

    // -- Deposit interest ---------------------------------------------------
    Component {
        id: interestCalculator
        CalculatorCard {
            heading: "Deposit interest"
            summary: "What a term deposit pays after the 5 % withholding tax."

            function run() { calc.interest(principal.text, rate.text, days.text) }

            Flow {
                width: parent.width
                spacing: 12
                Field { id: principal; width: 220; label: "Deposit (₺)"; placeholder: "0,00"; onAccepted: run() }
                Field { id: rate; width: 180; label: "Yearly interest (%)"; placeholder: "45"; onAccepted: run() }
                Field { id: days; width: 130; label: "Days"; placeholder: "32"; onAccepted: run() }
                RunButton { fieldHeight: principal.height; onClicked: run() }
            }
            Notice { width: parent.width; text: calc.message }
            Figures { width: parent.width; visible: calc.interestRows.length > 0; rows: calc.interestRows }
        }
    }

    // -- Compound growth ----------------------------------------------------
    Component {
        id: growthCalculator
        CalculatorCard {
            heading: "Compound growth"
            summary: "How a starting amount grows at a yearly return, with an optional monthly contribution."

            function run() { calc.growth(principal.text, rate.text, years.text, deposit.text) }

            Flow {
                width: parent.width
                spacing: 12
                Field { id: principal; width: 200; label: "Starting amount (₺)"; placeholder: "0,00"; onAccepted: run() }
                Field { id: rate; width: 160; label: "Yearly return (%)"; placeholder: "30"; onAccepted: run() }
                Field { id: years; width: 110; label: "Years"; placeholder: "5"; onAccepted: run() }
                Field { id: deposit; width: 220; label: "Monthly contribution (₺, optional)"; placeholder: "0,00"; onAccepted: run() }
                RunButton { fieldHeight: principal.height; onClicked: run() }
            }
            Notice { width: parent.width; text: calc.message }
            Figures { width: parent.width; visible: calc.growthRows.length > 0; rows: calc.growthRows }
            LineChart {
                width: parent.width
                height: 220
                visible: calc.growthSeries.length > 1
                values: calc.growthSeries
                labels: calc.growthLabels
            }
        }
    }

    // -- Time to a goal -----------------------------------------------------
    Component {
        id: goalCalculator
        CalculatorCard {
            heading: "Time to a goal"
            summary: "How long regular saving takes to reach an amount. The result can become a savings goal."

            property string period: "monthly"
            function run() { calc.goalTime(target.text, deposit.text, period === "daily") }

            Flow {
                width: parent.width
                spacing: 12
                Field { id: target; width: 220; label: "Target amount (₺)"; placeholder: "0,00"; onAccepted: run() }
                Field { id: deposit; width: 200; label: "Amount saved each time (₺)"; placeholder: "0,00"; onAccepted: run() }
                Item {
                    width: periodChoice.width
                    height: target.height
                    Segmented {
                        id: periodChoice
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 4
                        model: [{ key: "monthly", label: "Every month" }, { key: "daily", label: "Every day" }]
                        current: period
                        onChosen: function (key) { period = key }
                    }
                }
                RunButton { fieldHeight: target.height; onClicked: run() }
            }
            Notice { width: parent.width; text: calc.message }
            Figures { width: parent.width; visible: calc.goalRows.length > 0; rows: calc.goalRows }

            Flow {
                width: parent.width
                spacing: 12
                visible: calc.goalReady

                Field {
                    id: goalName
                    width: 260
                    label: "Create a savings goal named"
                    placeholder: "Holiday fund"
                    onAccepted: calc.createGoal(text)
                }
                RunButton {
                    fieldHeight: goalName.height
                    text: "Create goal"
                    onClicked: calc.createGoal(goalName.text)
                }
                Text {
                    height: goalName.height
                    verticalAlignment: Text.AlignBottom
                    bottomPadding: 10
                    text: calc.goalNote
                    color: Theme.up
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }
            }
        }
    }

    // -- Plain calculator ---------------------------------------------------
    Component {
        id: plainCalculator
        CalculatorCard {
            heading: "Calculator"
            summary: "Type an expression and press Enter. You can use + − × ÷, brackets, ^ for powers, and sqrt( )."

            Flow {
                width: parent.width
                spacing: 12
                Field {
                    id: expression
                    width: Math.min(parent.width - runPlain.width - 12, 520)
                    label: "Expression"
                    placeholder: "(1250 + 480) * 1,2"
                    onAccepted: calc.evaluate(text)
                    Component.onCompleted: input.forceActiveFocus()
                }
                RunButton { id: runPlain; fieldHeight: expression.height; text: "="; onClicked: calc.evaluate(expression.text) }
            }
            Notice { width: parent.width; text: calc.message }
            Text {
                visible: calc.answer.length > 0
                text: calc.answer
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 34
                font.weight: Font.Light
            }
        }
    }
}
