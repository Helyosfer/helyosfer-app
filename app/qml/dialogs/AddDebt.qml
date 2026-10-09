import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: "Add debt"
    subtitle: "A loan or any debt paid in fixed monthly installments."

    function openFresh() {
        name.text = ""
        monthly.text = ""
        count.text = ""
        day.text = "1"
        automatic.checked = false
        debts.clearMessage()
        open()
        name.input.forceActiveFocus()
    }

    function submit() {
        debts.addDebt(name.text, monthly.text, count.text, automatic.checked, day.text)
    }

    Connections {
        target: debts
        function onSaved() { if (root.visible) root.close() }
    }

    Field {
        id: name
        width: parent.width
        label: "Name"
        placeholder: "Car loan"
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: monthly
            width: (parent.width - 12) * 0.6
            label: "Monthly payment (₺)"
            placeholder: "0,00"
            money: true
            onAccepted: root.submit()
        }
        Field {
            id: count
            width: (parent.width - 12) * 0.4
            label: "Installments left"
            placeholder: "12"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
    }

    Row {
        width: parent.width
        spacing: 16

        Toggle {
            id: automatic
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 10
            text: "Pay automatically each month"
        }
        Field {
            id: day
            visible: automatic.checked
            width: 110
            label: "On day"
            placeholder: "1–31"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
    }

    Notice {
        width: parent.width
        problem: false
        visible: automatic.checked && debts.message.length === 0
        text: "Automatic installments are taken from your first account when you open Helysofer on or after that day."
    }

    Notice {
        width: parent.width
        text: debts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: debts.busy ? "Saving…" : "Add debt"
            enabled: !debts.busy && name.text.trim().length > 0
            onClicked: root.submit()
        }
    ]
}
