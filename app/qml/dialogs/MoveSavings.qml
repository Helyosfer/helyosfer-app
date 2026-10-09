import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Adds money to a goal, takes it back, or deletes the goal (`mode`).
Sheet {
    id: root
    property var goal: null
    property string mode: "deposit"

    readonly property bool deleting: mode === "delete"

    title: !goal ? ""
        : mode === "deposit" ? "Add to " + goal.name
        : mode === "withdraw" ? "Take from " + goal.name
        : "Delete " + goal.name + "?"
    subtitle: !goal ? ""
        : deleting
            ? (goal.hasMoney
               ? "The " + goal.savedText + " saved in it goes back to the account you choose."
               : "This goal holds no money. Deleting it cannot be undone.")
            : goal.savedText + " saved of " + goal.targetText

    function openFor(item, action) {
        goal = item
        mode = action
        amount.text = ""
        savings.clearMessage()
        if (accounts.checkingOptions.length === 1) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        open()
        if (!deleting) amount.input.forceActiveFocus()
    }

    function submit() {
        var key = account.currentKey === undefined ? -1 : account.currentKey
        if (deleting) savings.deleteGoal(goal.id, goal.uid, key)
        else savings.move(goal.id, goal.uid, amount.text, key, mode === "deposit")
    }

    Connections {
        target: savings
        function onSaved() { if (root.visible) root.close() }
    }

    Field {
        id: amount
        visible: !root.deleting
        width: parent.width
        label: "Amount (₺)"
        placeholder: "0,00"
        money: true
        onAccepted: root.submit()
    }

    Choice {
        id: account
        visible: !root.deleting || (root.goal !== null && root.goal.hasMoney)
        width: parent.width
        label: root.mode === "deposit" ? "Take from" : "Return to"
        placeholder: "Choose an account"
        model: accounts.checkingOptions
    }

    Notice {
        width: parent.width
        text: savings.message
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            quiet: root.deleting
            danger: root.deleting
            text: savings.busy ? "Working…"
                : root.mode === "deposit" ? "Add" : root.mode === "withdraw" ? "Take back" : "Delete goal"
            enabled: !savings.busy
            onClicked: root.submit()
        }
    ]
}
