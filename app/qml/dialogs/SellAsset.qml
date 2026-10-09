import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var holding: null

    title: holding ? qsTr("Sell %1").arg(holding.name) : ""
    subtitle: holding ? qsTr("You hold %1, bought at %2 each.").arg(holding.quantityText).arg(holding.costText) : ""

    function openFor(item) {
        holding = item
        quantity.text = item.quantityText
        price.text = item.priceForm
        assets.clearMessage()
        if (accounts.checkingOptions.length === 1) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        open()
        price.input.forceActiveFocus()
    }

    function submit() {
        assets.sell(holding.id, quantity.text, price.text,
                    account.currentKey === undefined ? -1 : account.currentKey)
    }

    Connections {
        target: assets
        function onSaved() { if (root.visible) root.close() }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: quantity
            width: (parent.width - 12) / 2
            label: qsTr("Quantity to sell")
            onAccepted: root.submit()
        }
        Field {
            id: price
            width: (parent.width - 12) / 2
            label: qsTr("Unit price (₺)")
            placeholder: "0,00"
            onAccepted: root.submit()
        }
    }

    Choice {
        id: account
        width: parent.width
        label: qsTr("Add the money to")
        placeholder: qsTr("Choose an account")
        model: accounts.checkingOptions
    }

    Notice {
        width: parent.width
        text: assets.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: assets.busy ? qsTr("Selling…") : qsTr("Sell")
            enabled: !assets.busy
            onClicked: root.submit()
        }
    ]
}
