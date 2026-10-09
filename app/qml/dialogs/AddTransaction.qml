import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: "Add transaction"

    property string kind: "expense"
    readonly property bool onCard: account.currentItem !== null
        && account.currentItem.kind === "credit_card" && kind === "expense"
    readonly property var chosenAccount: account.currentKey
    readonly property var chosenCategory: category.currentKey

    function openFor(accountKey) {
        kind = "expense"
        amount.text = ""
        description.text = ""
        date.text = transactions.todayText
        installments.select(1)
        transactions.clearMessage()
        if (accountKey >= 0) account.select(accountKey)
        else if (accounts.options.length === 1) account.select(accounts.options[0].key)
        else account.select(-1)
        category.select("")
        open()
        amount.input.forceActiveFocus()
    }

    function submit() {
        transactions.add(
            kind, amount.text,
            account.currentKey === undefined ? -1 : account.currentKey,
            category.currentKey === undefined ? "" : category.currentKey,
            description.text, date.text,
            onCard && installments.currentKey !== undefined ? installments.currentKey : 1)
    }

    onKindChanged: category.select("")

    Connections {
        target: transactions
        function onSaved() { if (root.opened) root.close() }
    }

    Segmented {
        model: [{ key: "expense", label: "Expense" }, { key: "income", label: "Income" }]
        current: root.kind
        onChosen: function (key) { root.kind = key }
    }

    Field {
        id: amount
        width: parent.width
        label: "Amount (₺)"
        placeholder: "0,00"
        input.inputMethodHints: Qt.ImhFormattedNumbersOnly
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12

        Choice {
            id: account
            width: (parent.width - 12) / 2
            label: "Account"
            placeholder: "Choose an account"
            model: accounts.options
        }
        Choice {
            id: category
            width: (parent.width - 12) / 2
            label: "Category"
            placeholder: "Choose a category"
            model: (transactions.categoryRevision, transactions.categories(root.kind))
        }
    }

    Choice {
        id: installments
        width: parent.width
        visible: root.onCard
        label: "Installments"
        model: {
            var options = [{ key: 1, label: "Single payment" }]
            for (var count = 2; count <= 12; count++)
                options.push({ key: count, label: count + " installments" })
            return options
        }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: description
            width: (parent.width - 12) * 0.62
            label: "Description (optional)"
            onAccepted: root.submit()
        }
        Field {
            id: date
            width: (parent.width - 12) * 0.38
            label: "Date"
            placeholder: "DD.MM.YYYY"
            onAccepted: root.submit()
        }
    }

    Notice {
        width: parent.width
        problem: false
        visible: transactions.message.length === 0
        text: "A future date is saved as a pending transaction and applied on that day."
    }

    Notice {
        width: parent.width
        text: transactions.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: transactions.busy ? "Saving…" : "Save"
            enabled: !transactions.busy
            onClicked: root.submit()
        }
    ]
}
