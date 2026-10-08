import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var editing: null
    property string kind: "expense"
    readonly property bool tracked: kind === "expense" && category.currentKey !== undefined
        && category.currentKey !== ""

    title: editing ? "Edit plan item" : "Add plan item"
    subtitle: editing && editing.everyMonth
        ? "This item repeats every month. Your change applies to " + budget.monthTitle + " only."
        : "For " + budget.monthTitle + ". Give spending a category to track it against what you actually spend."

    function openFresh() {
        editing = null
        kind = "expense"
        name.text = ""
        amount.text = ""
        everyMonth.checked = false
        rollover.checked = false
        threshold.text = "80"
        category.select("")
        budget.clearMessage()
        open()
        name.input.forceActiveFocus()
    }

    function openFor(item) {
        editing = item
        kind = item.kind
        name.text = item.name
        amount.text = item.amountForm
        everyMonth.checked = false
        rollover.checked = item.rollover
        threshold.text = item.threshold.toString()
        category.select(item.categoryKey)
        budget.clearMessage()
        open()
        amount.input.forceActiveFocus()
    }

    function submit() {
        budget.saveItem(editing ? editing.id : -1, kind, name.text, amount.text,
                        category.currentKey === undefined ? "" : category.currentKey,
                        everyMonth.checked, rollover.checked, threshold.text)
    }

    onKindChanged: if (!editing || kind !== editing.kind) category.select("")

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
        visible: root.editing === null
        text: "Use this for every month"
    }

    Row {
        width: parent.width
        spacing: 16
        visible: root.tracked

        Toggle {
            id: rollover
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 10
            text: "Carry what is left into next month"
        }
        Field {
            id: threshold
            width: 120
            label: "Warn at (%)"
            placeholder: "80"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
    }

    Notice {
        width: parent.width
        text: budget.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: budget.busy ? "Saving…" : (root.editing ? "Save" : "Add")
            enabled: !budget.busy
            onClicked: root.submit()
        }
    ]
}
