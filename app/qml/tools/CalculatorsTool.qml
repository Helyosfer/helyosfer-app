import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    property string calculator: "loan"
    spacing: Theme.gap

    Segmented {
        model: [
            { key: "loan", label: qsTr("Loan") },
            { key: "interest", label: qsTr("Deposit interest") },
            { key: "growth", label: qsTr("Compound growth") },
            { key: "goal", label: qsTr("Time to a goal") },
            { key: "plain", label: qsTr("Calculator") }
        ]
        current: root.calculator
        onChosen: function (key) { calc.clearMessage(); root.calculator = key }
    }

    Loader {
        width: parent.width
        sourceComponent: root.calculator === "loan" ? loanCalculator : smallCalculator
    }

    Component { id: loanCalculator; LoanTool {} }
    Component { id: smallCalculator; SmallCalculators { which: root.calculator } }
}
