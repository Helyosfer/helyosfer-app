import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: qsTr("Add recurring payment")

    property string kind: "expense"

    function openFresh() {
        kind = "expense"
        name.text = ""
        amount.text = ""
        firstDue.text = transactions.todayText
        automatic.checked = true
        frequency.select("monthly")
        category.select("")
        recurring.clearMessage()
        if (accounts.options.length === 1) account.select(accounts.options[0].key)
        else account.select(-1)
        open()
        name.input.forceActiveFocus()
    }

    function submit() {
        recurring.add(kind, name.text, amount.text,
                      category.currentKey === undefined ? "" : category.currentKey,
                      frequency.currentKey === undefined ? "monthly" : frequency.currentKey,
                      firstDue.text, automatic.checked,
                      account.currentKey === undefined ? -1 : account.currentKey)
    }

    onKindChanged: category.select("")

    Connections {
        target: recurring
        function onSaved() { if (root.visible) root.close() }
    }

    Segmented {
        model: [{ key: "expense", label: qsTr("Payment") }, { key: "income", label: qsTr("Income") }]
        current: root.kind
        onChosen: function (key) { root.kind = key }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: name
            width: (parent.width - 12) * 0.6
            label: qsTr("Name")
            placeholder: root.kind === "income" ? qsTr("Salary") : qsTr("Music subscription")
            onAccepted: root.submit()
        }
        Field {
            id: amount
            width: (parent.width - 12) * 0.4
            label: qsTr("Amount (₺)")
            placeholder: "0,00"
            money: true
            onAccepted: root.submit()
        }
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
        }
        Choice {
            id: category
            width: (parent.width - 12) / 2
            label: qsTr("Category")
            placeholder: qsTr("Choose a category")
            model: (transactions.categoryRevision, transactions.categories(root.kind))
        }
    }

    Row {
        width: parent.width
        spacing: 12

        Choice {
            id: frequency
            width: (parent.width - 12) * 0.6
            label: qsTr("Repeats")
            model: recurring.frequencies
        }
        Field {
            id: firstDue
            width: (parent.width - 12) * 0.4
            label: qsTr("Next due")
            placeholder: qsTr("DD.MM.YYYY")
            onAccepted: root.submit()
        }
    }

    Toggle {
        id: automatic
        text: root.kind === "income" ? qsTr("Add to the account automatically when due")
                                     : qsTr("Take from the account automatically when due")
    }

    Notice {
        width: parent.width
        problem: false
        visible: automatic.checked && recurring.message.length === 0
        text: qsTr("Each automatic payment is recorded on its due day, even if Helyosfer is opened later. A date in the past records every payment since then.")
    }

    Notice {
        width: parent.width
        text: recurring.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: recurring.busy ? qsTr("Saving…") : qsTr("Add")
            enabled: !recurring.busy
            onClicked: root.submit()
        }
    ]
}
