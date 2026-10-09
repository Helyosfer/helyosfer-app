import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: qsTr("Add account")

    property string kind: "checking"
    readonly property bool credit: kind === "credit_card"
    readonly property string typedDigits: cardNumber.text.replace(/[^0-9]/g, "")

    // The network a number belongs to, from its first digits, for the preview.
    function networkOf(digits) {
        if (digits.length === 0) return ""
        if (digits[0] === "4") return "Visa"
        var two = parseInt(digits.substring(0, 2))
        var four = parseInt(digits.substring(0, 4))
        if ((two >= 51 && two <= 55) || (four >= 2221 && four <= 2720)) return "Mastercard"
        if (digits.substring(0, 4) === "9792" || digits.substring(0, 2) === "65") return "Troy"
        return ""
    }

    // The preview is left out where the window is too short to hold it
    // together with the form.
    readonly property bool roomy: parent ? parent.height >= 780 : true
    readonly property bool previewing: credit && roomy

    onPreviewingChanged: if (previewing) preview.play()

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
        function onSaved() { if (root.visible) root.close() }
    }

    Segmented {
        model: [{ key: "checking", label: qsTr("Cash or checking") }, { key: "credit_card", label: qsTr("Credit card") }]
        current: root.kind
        onChosen: function (key) { root.kind = key }
    }

    // The card itself, filling in as it is typed. It takes its room only
    // for a credit card.
    Item {
        width: parent.width
        height: root.previewing ? preview.height + 6 : 0
        opacity: root.previewing ? 1 : 0
        clip: !root.previewing
        Behavior on height { NumberAnimation { duration: Theme.medium; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.medium } }

        CardVisual {
            id: preview
            objectName: "cardPreview"
            width: Math.min(270, parent.width)
            anchors.horizontalCenter: parent.horizontalCenter
            holder: name.text.trim().length > 0 ? name.text : qsTr("Card name")
            digits: root.typedDigits
            network: root.networkOf(root.typedDigits)
        }
    }

    Field {
        id: name
        width: parent.width
        label: qsTr("Name")
        placeholder: root.credit ? qsTr("Card name") : qsTr("Account name")
        onAccepted: root.submit()
    }

    Field {
        id: balance
        width: parent.width
        label: root.credit ? qsTr("Current debt (₺)") : qsTr("Current balance (₺)")
        placeholder: "0,00"
        money: true
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12
        visible: root.credit

        Field {
            id: limit
            width: (parent.width - 12) * 0.62
            label: qsTr("Card limit (₺)")
            placeholder: "0,00"
            money: true
            onAccepted: root.submit()
        }
        Field {
            id: statementDay
            width: (parent.width - 12) * 0.38
            label: qsTr("Statement day")
            placeholder: "1–31"
            input.inputMethodHints: Qt.ImhDigitsOnly
            onAccepted: root.submit()
        }
    }

    Field {
        id: cardNumber
        width: parent.width
        label: qsTr("Card number (optional)")
        placeholder: qsTr("Used only to show the last four digits")
        input.inputMethodHints: Qt.ImhDigitsOnly
        onAccepted: root.submit()
    }

    Notice {
        width: parent.width
        problem: false
        visible: accounts.message.length === 0
        text: qsTr("Only the last four digits and the card network are kept. The full number is never stored.")
    }

    Notice {
        width: parent.width
        text: accounts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: accounts.busy ? qsTr("Saving…") : qsTr("Add account")
            enabled: !accounts.busy && name.text.trim().length > 0
            onClicked: root.submit()
        }
    ]
}
