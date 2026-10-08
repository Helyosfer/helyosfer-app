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
            { key: "loan", label: "Loan" },
            { key: "interest", label: "Deposit interest" },
            { key: "growth", label: "Compound growth" },
            { key: "goal", label: "Time to a goal" },
            { key: "plain", label: "Calculator" }
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
