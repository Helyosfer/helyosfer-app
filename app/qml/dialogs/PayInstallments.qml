import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var debt: null
    property bool closing: false

    title: closing ? qsTr("Pay off this debt") : qsTr("Pay installments")
    subtitle: debt
        ? debt.name + "  ·  " + (debt.remainingCount === 1
              ? qsTr("%1 left in 1 installment").arg(debt.remainingText)
              : qsTr("%1 left in %2 installments").arg(debt.remainingText).arg(debt.remainingCount))
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
        label: qsTr("Pay from")
        placeholder: qsTr("Choose an account")
        model: accounts.checkingOptions
    }

    Field {
        id: count
        visible: !root.closing
        width: parent.width
        label: root.debt ? qsTr("Installments to pay (1–%1)").arg(root.debt.remainingCount) : ""
        input.inputMethodHints: Qt.ImhDigitsOnly
        onAccepted: root.submit()
    }

    Notice {
        width: parent.width
        problem: false
        visible: debts.message.length === 0 && root.debt !== null
        text: root.closing
            ? qsTr("%1 will be taken from the account and the debt closed.").arg(root.debt.remainingText)
            : qsTr("Each installment is %1.").arg(root.debt ? root.debt.monthlyText : "")
    }

    Notice {
        width: parent.width
        text: debts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: debts.busy ? qsTr("Paying…") : (root.closing ? qsTr("Pay off") : qsTr("Pay"))
            enabled: !debts.busy
            onClicked: root.submit()
        }
    ]
}
