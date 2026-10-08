import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: "Add plan item"
    subtitle: "For " + budget.monthTitle + ". Give spending a category to track it against what you actually spend."

    property string kind: "expense"

    function openFresh() {
        kind = "expense"
        name.text = ""
        amount.text = ""
        everyMonth.checked = false
        category.select("")
        budget.clearMessage()
        open()
        name.input.forceActiveFocus()
    }

    function submit() {
        budget.addItem(kind, name.text, amount.text,
                       category.currentKey === undefined ? "" : category.currentKey,
                       everyMonth.checked)
    }

    onKindChanged: category.select("")

    Connections {
        target: budget
        function onSaved() { if (root.visible) root.close() }
    }

    Segmented {
        model: [{ key: "expense", label: "Spending" }, { key: "income", label: "Income" }]
        current: root.kind
        onChosen: function (key) { root.kind = key }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: name
            width: (parent.width - 12) * 0.6
            label: "Name"
            placeholder: root.kind === "income" ? "Salary" : "Groceries"
            onAccepted: root.submit()
        }
        Field {
            id: amount
            width: (parent.width - 12) * 0.4
            label: "Amount (₺)"
            placeholder: "0,00"
            onAccepted: root.submit()
        }
    }

    Choice {
        id: category
        width: parent.width
        label: "Category (optional)"
        placeholder: "No category"
        model: transactions.categories(root.kind)
    }

    Toggle {
        id: everyMonth
        text: "Use this for every month"
    }

    Notice {
        width: parent.width
        text: budget.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: budget.busy ? "Saving…" : "Add"
            enabled: !budget.busy
            onClicked: root.submit()
        }
    ]
}
