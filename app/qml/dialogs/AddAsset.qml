import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: "Add asset"
    subtitle: "Record something you bought. Prices are entered and shown in lira."

    readonly property string kind: type.currentKey === undefined ? "" : type.currentKey
    readonly property bool gold: kind === "Altın"

    function openFresh() {
        type.select("Hisse")
        goldKind.select("GC=F")
        code.text = ""
        name.text = ""
        quantity.text = ""
        price.text = ""
        deduct.checked = true
        assets.clearMessage()
        assets.clearQuote()
        if (accounts.checkingOptions.length === 1) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        open()
        code.input.forceActiveFocus()
    }

    function symbol() { return gold ? (goldKind.currentKey === undefined ? "" : goldKind.currentKey) : code.text }

    function submit() {
        assets.buy(kind, symbol(), name.text, quantity.text, price.text,
                   account.currentKey === undefined ? -1 : account.currentKey, deduct.checked)
    }

    Connections {
        target: assets
        function onSaved() { if (root.visible) root.close() }
        function onQuoteChanged() { if (root.visible && assets.quote.length > 0) price.text = assets.quote }
    }

    Row {
        width: parent.width
        spacing: 12

        Choice {
            id: type
            width: (parent.width - 12) * 0.4
            label: "Kind"
            model: assets.types
        }
        Field {
            id: code
            visible: !root.gold
            width: (parent.width - 12) * 0.6
            label: "Symbol"
            placeholder: assets.codeHint(root.kind)
            onAccepted: root.submit()
        }
        Choice {
            id: goldKind
            visible: root.gold
            width: (parent.width - 12) * 0.6
            label: "Type of gold"
            model: assets.goldKinds
        }
    }

    Field {
        id: name
        visible: !root.gold
        width: parent.width
        label: "Name (optional)"
        placeholder: "Shown in your list instead of the symbol"
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: quantity
            width: (parent.width - 24) * 0.3
            label: "Quantity"
            placeholder: "0"
            onAccepted: root.submit()
        }
        Field {
            id: price
            width: (parent.width - 24) * 0.4
            label: "Unit price (₺)"
            placeholder: "0,00"
            onAccepted: root.submit()
        }
        PrimaryButton {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
            width: (parent.width - 24) * 0.3
            quiet: true
            text: assets.quoteBusy ? "Looking up…" : "Current price"
            enabled: !assets.quoteBusy
            onClicked: assets.lookUp(root.kind, root.symbol())
        }
    }

    Toggle {
        id: deduct
        text: "Take the cost from an account"
    }

    Choice {
        id: account
        visible: deduct.checked
        width: parent.width
        label: "Pay from"
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
            text: assets.busy ? "Saving…" : "Add asset"
            enabled: !assets.busy
            onClicked: root.submit()
        }
    ]
}
