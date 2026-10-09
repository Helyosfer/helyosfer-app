import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: editing >= 0 ? qsTr("Edit transaction") : qsTr("Add transaction")

    property string kind: "expense"
    // The transaction being changed, or -1 while adding a new one.
    property int editing: -1
    // Why the transaction cannot be changed; empty when it can.
    property string locked: ""
    property bool confirming: false
    readonly property bool onCard: account.currentItem !== null
        && account.currentItem.kind === "credit_card" && kind === "expense"
    readonly property var chosenAccount: account.currentKey
    readonly property var chosenCategory: category.currentKey

    function openForEdit(transactionId) {
        var found = transactions.details(transactionId)
        if (found.id === undefined) return
        transactions.clearMessage()
        editing = transactionId
        locked = found.locked
        confirming = false
        kind = found.kind
        amount.text = found.amountText
        description.text = found.description
        date.text = found.dateText
        installments.select(1)
        account.select(found.accountId)
        category.select(found.category)
        open()
        if (locked.length === 0) amount.input.forceActiveFocus()
    }

    function openFor(accountKey) {
        editing = -1
        locked = ""
        confirming = false
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
        if (locked.length > 0) return
        if (editing >= 0) {
            transactions.update(editing, amount.text,
                                category.currentKey === undefined ? "" : category.currentKey,
                                description.text, date.text)
            return
        }
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
        function onSaved() { if (root.visible) root.close() }
    }

    Segmented {
        model: [{ key: "expense", label: qsTr("Expense") }, { key: "income", label: qsTr("Income") }]
        current: root.kind
        // The direction and the account of a saved transaction stay as they are.
        enabled: root.editing < 0
        opacity: enabled ? 1 : 0.55
        onChosen: function (key) { root.kind = key }
    }

    Field {
        id: amount
        width: parent.width
        enabled: root.locked.length === 0
        label: qsTr("Amount (₺)")
        placeholder: "0,00"
        money: true
        input.inputMethodHints: Qt.ImhFormattedNumbersOnly
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12

        Choice {
            id: account
            width: (parent.width - 12) / 2
            label: qsTr("Account")
            placeholder: qsTr("Choose an account")
            model: accounts.options
            enabled: root.editing < 0
            opacity: enabled ? 1 : 0.55
        }
        Choice {
            id: category
            width: (parent.width - 12) / 2
            label: qsTr("Category")
            placeholder: qsTr("Choose a category")
            model: (transactions.categoryRevision, transactions.categories(root.kind))
            enabled: root.locked.length === 0
        }
    }

    Choice {
        id: installments
        width: parent.width
        visible: root.onCard && root.editing < 0
        label: qsTr("Installments")
        model: {
            var options = [{ key: 1, label: qsTr("Single payment") }]
            for (var count = 2; count <= 12; count++)
                options.push({ key: count, label: qsTr("%1 installments").arg(count) })
            return options
        }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: description
            width: (parent.width - 12) * 0.62
            label: qsTr("Description (optional)")
            enabled: root.locked.length === 0
            onAccepted: root.submit()
        }
        Field {
            id: date
            width: (parent.width - 12) * 0.38
            label: qsTr("Date")
            enabled: root.locked.length === 0
            placeholder: qsTr("DD.MM.YYYY")
            onAccepted: root.submit()
        }
    }

    Notice {
        width: parent.width
        problem: false
        visible: transactions.message.length === 0 && root.editing < 0
        text: qsTr("A future date is saved as a pending transaction and applied on that day.")
    }

    Notice {
        width: parent.width
        problem: false
        visible: root.locked.length > 0
        text: root.locked
    }

    Notice {
        width: parent.width
        text: transactions.message
    }

    footer: [
        PrimaryButton {
            quiet: true
            danger: true
            visible: root.editing >= 0 && root.locked.length === 0
            text: root.confirming ? qsTr("Delete for good") : qsTr("Delete")
            enabled: !transactions.busy
            onClicked: {
                if (root.confirming) transactions.remove(root.editing)
                else root.confirming = true
            }
        },
        PrimaryButton {
            quiet: true
            text: root.locked.length > 0 ? qsTr("Close") : qsTr("Cancel")
            onClicked: root.close()
        },
        PrimaryButton {
            visible: root.locked.length === 0
            text: transactions.busy ? qsTr("Saving…") : qsTr("Save")
            enabled: !transactions.busy
            onClicked: root.submit()
        }
    ]
}
