import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: qsTr("Add debt")
    subtitle: qsTr("A loan or any debt paid in fixed monthly installments.")

    function openFresh() {
        name.text = ""
        monthly.text = ""
        count.text = ""
        day.text = "1"
        automatic.checked = false
        if (accounts.checkingOptions.length > 0) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        debts.clearMessage()
        open()
        name.input.forceActiveFocus()
    }

    function submit() {
        debts.addDebt(name.text, monthly.text, count.text, automatic.checked, day.text,
                      account.currentKey === undefined ? -1 : account.currentKey)
    }

    Connections {
        target: debts
        function onSaved() { if (root.visible) root.close() }
    }

    Field {
        id: name
        width: parent.width
        label: qsTr("Name")
        placeholder: qsTr("Car loan")
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: monthly
            width: (parent.width - 12) * 0.6
            label: qsTr("Monthly payment (₺)")
            placeholder: "0,00"
            money: true
            onAccepted: root.submit()
        }
        Field {
            id: count
            width: (parent.width - 12) * 0.4
            label: qsTr("Installments left")
            placeholder: "12"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
    }

    Toggle {
        id: automatic
        text: qsTr("Pay automatically each month")
    }

    Row {
        width: parent.width
        spacing: 12
        visible: automatic.checked

        Field {
            id: day
            width: (parent.width - 12) * 0.35
            label: qsTr("On day")
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
        visible: automatic.checked && debts.message.length === 0
        text: qsTr("The first automatic installment is the next one. Each is recorded on its day, even if Helyosfer is opened later.")
    }

    Notice {
        width: parent.width
        text: debts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: debts.busy ? qsTr("Saving…") : qsTr("Add debt")
            enabled: !debts.busy && name.text.trim().length > 0
            onClicked: root.submit()
        }
    ]
}
