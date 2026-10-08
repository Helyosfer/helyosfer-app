import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var holding: null

    title: holding ? "Sell " + holding.name : ""
    subtitle: holding ? "You hold " + holding.quantityText + ", bought at " + holding.costText + " each." : ""

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
            label: "Quantity to sell"
            onAccepted: root.submit()
        }
        Field {
            id: price
            width: (parent.width - 12) / 2
            label: "Unit price (₺)"
            placeholder: "0,00"
            onAccepted: root.submit()
        }
    }

    Choice {
        id: account
        width: parent.width
        label: "Add the money to"
        placeholder: "Choose an account"
        model: accounts.checkingOptions
    }

    Notice {
        width: parent.width
        text: assets.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: assets.busy ? "Selling…" : "Sell"
            enabled: !assets.busy
            onClicked: root.submit()
        }
    ]
}
