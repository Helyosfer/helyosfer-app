import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var card: null

    title: "Pay card debt"
    subtitle: card ? card.name + "  ·  " + card.debtText + " owed" : ""

    function openFor(account) {
        card = account
        amount.text = ""
        accounts.clearMessage()
        if (accounts.checkingOptions.length === 1) source.select(accounts.checkingOptions[0].key)
        else source.select(-1)
        open()
        amount.input.forceActiveFocus()
    }

    function submit() {
        accounts.payDebt(card.id, source.currentKey === undefined ? -1 : source.currentKey, amount.text)
    }

    Connections {
        target: accounts
        function onSaved() { if (root.opened) root.close() }
    }

    Choice {
        id: source
        width: parent.width
        label: "Pay from"
        placeholder: "Choose an account"
        model: accounts.checkingOptions
    }

    Field {
        id: amount
        width: parent.width
        label: "Amount (₺)"
        placeholder: "0,00"
        onAccepted: root.submit()
    }

    Notice {
        width: parent.width
        text: accounts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: accounts.busy ? "Paying…" : "Pay"
            enabled: !accounts.busy
            onClicked: root.submit()
        }
    ]
}
