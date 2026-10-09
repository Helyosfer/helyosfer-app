import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Turns automatic payment on for a debt: the day of the month and the
// account the installments are taken from.
Sheet {
    id: root
    property var subject: null

    title: qsTr("Pay automatically")
    subtitle: subject ? qsTr("%1 is taken for %2 each month.").arg(subject.monthlyText).arg(subject.name) : ""

    function openFor(debt, initialDay) {
        subject = debt
        day.text = initialDay === undefined || initialDay === "" ? "1" : initialDay
        if (accounts.checkingOptions.length > 0) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        debts.clearMessage()
        open()
        day.input.forceActiveFocus()
        day.input.selectAll()
    }

    function submit() {
        debts.setAutoPay(subject.id, true, day.text,
                         account.currentKey === undefined ? -1 : account.currentKey)
    }

    Connections {
        target: debts
        function onSaved() { if (root.visible) root.close() }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: day
            width: (parent.width - 12) * 0.35
            label: qsTr("Day of the month (1–31)")
            placeholder: "1–31"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
        Choice {
            id: account
            width: (parent.width - 12) * 0.65
            label: qsTr("Pay from")
            placeholder: qsTr("Choose an account")
            model: accounts.checkingOptions
        }
    }

    Notice {
        width: parent.width
        problem: false
        visible: debts.message.length === 0
        text: qsTr("The first automatic installment is the next one. Each is recorded on its day, even if Helyosfer is opened later.")
    }

    Notice {
        width: parent.width
        text: debts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: qsTr("Turn on")
            enabled: !debts.busy
            onClicked: root.submit()
        }
    ]
}
