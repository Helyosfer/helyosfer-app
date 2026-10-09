import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var card: null

    title: qsTr("Pay card debt")
    subtitle: card ? card.name + "  ·  " + qsTr("%1 owed").arg(card.debtText) : ""

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
        id: amount
        width: parent.width
        label: qsTr("Amount (₺)")
        placeholder: "0,00"
        money: true
        onAccepted: root.submit()
    }

    Notice {
        width: parent.width
        text: accounts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: accounts.busy ? qsTr("Paying…") : qsTr("Pay")
            enabled: !accounts.busy
            onClicked: root.submit()
        }
    ]
}
