import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: "Add account"

    property string kind: "checking"
    readonly property bool credit: kind === "credit_card"

    function openFresh() {
        kind = "checking"
        name.text = ""
        balance.text = ""
        limit.text = ""
        statementDay.text = ""
        cardNumber.text = ""
        accounts.clearMessage()
        open()
        name.input.forceActiveFocus()
    }

    function submit() {
        accounts.addAccount(kind, name.text, balance.text, limit.text,
                            statementDay.text, cardNumber.text)
    }

    Connections {
        target: accounts
        function onSaved() { if (root.opened) root.close() }
    }

    Segmented {
        model: [{ key: "checking", label: "Cash or checking" }, { key: "credit_card", label: "Credit card" }]
        current: root.kind
        onChosen: function (key) { root.kind = key }
    }

    Field {
        id: name
        width: parent.width
        label: "Name"
        placeholder: root.credit ? "Card name" : "Account name"
        onAccepted: root.submit()
    }

    Field {
        id: balance
        width: parent.width
        label: root.credit ? "Current debt (₺)" : "Current balance (₺)"
        placeholder: "0,00"
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12
        visible: root.credit

        Field {
            id: limit
            width: (parent.width - 12) * 0.62
            label: "Card limit (₺)"
            placeholder: "0,00"
            onAccepted: root.submit()
        }
        Field {
            id: statementDay
            width: (parent.width - 12) * 0.38
            label: "Statement day"
            placeholder: "1–31"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
    }

    Field {
        id: cardNumber
        width: parent.width
        label: "Card number (optional)"
        placeholder: "Used only to show the last four digits"
        input.inputMethodHints: Qt.ImhDigitsOnly
        onAccepted: root.submit()
    }

    Notice {
        width: parent.width
        problem: false
        visible: accounts.message.length === 0
        text: "Only the last four digits and the card network are kept. The full number is never stored."
    }

    Notice {
        width: parent.width
        text: accounts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: accounts.busy ? "Saving…" : "Add account"
            enabled: !accounts.busy && name.text.trim().length > 0
            onClicked: root.submit()
        }
    ]
}
