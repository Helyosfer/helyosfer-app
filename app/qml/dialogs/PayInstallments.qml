import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var debt: null
    property bool closing: false

    title: closing ? "Pay off this debt" : "Pay installments"
    subtitle: debt
        ? debt.name + "  ·  " + debt.remainingText + " left in " + debt.remainingCount
          + (debt.remainingCount === 1 ? " installment" : " installments")
        : ""

    function openFor(item, payOff) {
        debt = item
        closing = payOff
        count.text = "1"
        debts.clearMessage()
        if (accounts.checkingOptions.length === 1) source.select(accounts.checkingOptions[0].key)
        else source.select(-1)
        open()
    }

    function submit() {
        var installments = closing ? 0 : parseInt(count.text)
        if (!closing && (isNaN(installments) || installments < 1)) installments = -1
        debts.pay(debt.id, source.currentKey === undefined ? -1 : source.currentKey, installments)
    }

    Connections {
        target: debts
        function onSaved() { if (root.visible) root.close() }
    }

    Choice {
        id: source
        width: parent.width
        label: "Pay from"
        placeholder: "Choose an account"
        model: accounts.checkingOptions
    }

    Field {
        id: count
        visible: !root.closing
        width: parent.width
        label: root.debt ? "Installments to pay (1–" + root.debt.remainingCount + ")" : ""
        input.inputMethodHints: Qt.ImhDigitsOnly
        onAccepted: root.submit()
    }

    Notice {
        width: parent.width
        problem: false
        visible: debts.message.length === 0 && root.debt !== null
        text: root.closing
            ? root.debt.remainingText + " will be taken from the account and the debt closed."
            : "Each installment is " + (root.debt ? root.debt.monthlyText : "") + "."
    }

    Notice {
        width: parent.width
        text: debts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: debts.busy ? "Paying…" : (root.closing ? "Pay off" : "Pay")
            enabled: !debts.busy
            onClicked: root.submit()
        }
    ]
}
