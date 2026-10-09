import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import ".."
import "../components"
import "../dialogs"

Item {
    id: root

    // One setting: what it is on the left, its action on the right.
    component SettingRow: Item {
        id: setting
        property string title: ""
        property string detail: ""
        property bool warning: false
        default property alias actions: actionRow.data

        width: parent.width
        height: Math.max(texts.height, actionRow.height) + 24

        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

        Column {
            id: texts
            anchors.left: parent.left
            anchors.right: actionRow.left
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 3

            Text {
                width: parent.width
                text: setting.title
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 14
                wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                visible: setting.detail.length > 0
                text: setting.detail
                color: setting.warning ? Theme.warn : Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                lineHeight: 1.25
                wrapMode: Text.WordWrap
            }
        }

        Row {
            id: actionRow
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
        }
    }

    component Section: Card {
        property string heading: ""
        default property alias rows: sectionBody.data
        width: parent.width

        Column {
            id: sectionBody
            width: parent.width

            Text {
                bottomPadding: 10
                text: heading
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
    }

    Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
            id: page
            x: 28
            y: 24
            width: Math.min(scroller.width - 56, 860)
            spacing: Theme.gap

            Text {
                text: "Settings"
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 22
                font.weight: Font.Light
            }

            Rectangle {
                width: parent.width
                visible: settings.notice.length > 0 || settings.message.length > 0
                height: outcome.height + 24
                radius: Theme.radius
                color: Theme.raised
                border.width: 1
                border.color: settings.message.length > 0 ? Theme.down : Theme.line

                Text {
                    id: outcome
                    anchors.verticalCenter: parent.verticalCenter
                    x: 16
                    width: parent.width - 32
                    text: settings.message.length > 0 ? settings.message : settings.notice
                    color: settings.message.length > 0 ? Theme.down : Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
            }

            Section {
                heading: "Appearance"
                SettingRow {
                    title: "Dark theme"
                    detail: "Applies immediately and is remembered on this device."
                    Toggle {
                        checked: app.dark
                        onToggled: app.toggleTheme()
                    }
                }
            }

            Section {
                heading: "Security"
                SettingRow {
                    title: "Password"
                    detail: "You will be asked to sign in again after changing it."
                    PrimaryButton {
                        compact: true; quiet: true
                        text: "Change password"
                        onClicked: passwordDialog.openFresh()
                    }
                }
                SettingRow {
                    title: "Encryption key"
                    detail: settings.keyWarning.length > 0
                        ? settings.keyProtection + " — " + settings.keyWarning
                        : "Protected by " + settings.keyProtection + "."
                    warning: settings.keyWarning.length > 0
                }
            }

            Section {
                heading: "Backup"
                SettingRow {
                    title: "Create a backup"
                    detail: "One encrypted file with your records, the encryption key and your settings. It is protected by a separate backup password."
                    PrimaryButton {
                        compact: true; quiet: true
                        text: "Create backup"
                        onClicked: backupDialog.openFresh()
                    }
                }
                SettingRow {
                    title: "Restore from a backup"
                    detail: "Replaces everything on this device with the backup's contents. A safety copy of the current state is kept next to your data."
                    PrimaryButton {
                        compact: true; quiet: true
                        text: "Restore"
                        enabled: !settings.busy
                        onClicked: restoreFile.open()
                    }
                }
            }

            Section {
                heading: "Import and export"
                SettingRow {
                    title: "Export to CSV"
                    detail: "Transactions, assets, debts and recurring payments in one spreadsheet file. The file is not encrypted."
                    PrimaryButton {
                        compact: true; quiet: true
                        text: "Export"
                        enabled: !settings.busy
                        onClicked: exportFile.open()
                    }
                }
                SettingRow {
                    title: "Import transactions from CSV"
                    detail: "Adds the transactions in a CSV file to one of your accounts. Rows that cannot be read are skipped."
                    PrimaryButton {
                        compact: true; quiet: true
                        text: "Import"
                        enabled: !settings.busy
                        onClicked: importFile.open()
                    }
                }
            }

            Section {
                id: categorySection
                heading: "Categories"
                property string kind: "expense"

                Component.onCompleted: categories.refresh()

                Item {
                    width: parent.width
                    height: kindChoice.height + 12

                    Text {
                        anchors.verticalCenter: kindChoice.verticalCenter
                        width: parent.width - kindChoice.width - 24
                        text: "Essential categories are counted as needs in summaries and the health score; the rest as extras."
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Segmented {
                        id: kindChoice
                        anchors.right: parent.right
                        model: [{ key: "expense", label: "Spending" }, { key: "income", label: "Income" }]
                        current: categorySection.kind
                        onChosen: function (key) { categorySection.kind = key }
                    }
                }

                // Only the visible rows exist; the list scrolls on its own.
                ListView {
                    width: parent.width
                    height: 264
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    model: categories.items.filter(function (item) { return item.kind === categorySection.kind })

                    delegate: Item {
                        id: categoryRow
                        required property var modelData
                        width: ListView.view.width
                        height: 44

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.right: own.left
                            anchors.rightMargin: 16
                            text: categoryRow.modelData.name
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Row {
                            id: own
                            anchors.right: essential.left
                            anchors.rightMargin: 20
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8
                            visible: categoryRow.modelData.custom

                            PrimaryButton {
                                quiet: true
                                compact: true
                                text: "Rename"
                                onClicked: renamePrompt.openFor(categoryRow.modelData, categoryRow.modelData.name)
                            }
                            PrimaryButton {
                                quiet: true
                                danger: true
                                compact: true
                                text: "Remove"
                                enabled: !categories.busy
                                onClicked: categories.remove(categoryRow.modelData.key)
                            }
                        }
                        Toggle {
                            id: essential
                            anchors.right: parent.right
                            anchors.rightMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Essential"
                            checked: categoryRow.modelData.essential
                            onToggled: categories.setEssential(categoryRow.modelData.key, checked)
                        }
                    }
                }

                Item {
                    width: parent.width
                    height: newCategory.height + 20

                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                    Row {
                        anchors.bottom: parent.bottom
                        spacing: 12

                        Field {
                            id: newCategory
                            width: 260
                            label: categorySection.kind === "income" ? "New income category" : "New spending category"
                            placeholder: "Name"
                            onAccepted: categories.add(categorySection.kind, text, newEssential.checked)
                        }
                        Item {
                            width: newEssential.width
                            height: newCategory.height
                            Toggle {
                                id: newEssential
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 10
                                text: "Essential"
                            }
                        }
                        Item {
                            width: addCategory.width
                            height: newCategory.height
                            PrimaryButton {
                                id: addCategory
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 2
                                quiet: true
                                text: "Add category"
                                enabled: !categories.busy && newCategory.text.trim().length > 0
                                onClicked: categories.add(categorySection.kind, newCategory.text, newEssential.checked)
                            }
                        }
                    }
                }

                Connections {
                    target: categories
                    function onSaved() { newCategory.text = "" }
                }

                Notice {
                    width: parent.width
                    text: categories.message
                }
            }

            Section {
                heading: "Danger zone"
                SettingRow {
                    title: "Delete all data"
                    detail: "Erases every account, transaction, debt and setting, and your password. This cannot be undone; create a backup first."
                    PrimaryButton {
                        compact: true; quiet: true; danger: true
                        text: "Delete everything"
                        onClicked: resetDialog.openFor(null, "")
                    }
                }
            }

            Section {
                heading: "About"
                SettingRow {
                    title: "Helysofer " + app.version
                    detail: "Questions, feedback and bug reports: " + settings.projectUrl
                        + "  ·  " + settings.contactEmail
                }
                SettingRow {
                    title: "Where your data is kept"
                    detail: settings.dataFolder
                }
            }
        }
    }

    // -- Dialogs --------------------------------------------------------------
    Sheet {
        id: passwordDialog
        objectName: "passwordDialog"
        title: "Change password"

        function openFresh() {
            current.text = ""; next.text = ""; again.text = ""
            settings.clearMessage()
            open()
            current.input.forceActiveFocus()
        }
        function submit() { settings.changePassword(current.text, next.text, again.text) }

        Connections {
            target: settings
            function onSaved() { if (passwordDialog.visible) passwordDialog.close() }
        }

        Field {
            id: current
            width: parent.width
            label: "Current password"
            echoMode: TextInput.Password
            onAccepted: next.input.forceActiveFocus()
        }
        Field {
            id: next
            width: parent.width
            label: "New password"
            echoMode: TextInput.Password
            onAccepted: again.input.forceActiveFocus()
        }
        Field {
            id: again
            width: parent.width
            label: "Repeat new password"
            echoMode: TextInput.Password
            onAccepted: passwordDialog.submit()
        }
        Notice {
            width: parent.width
            problem: false
            visible: settings.message.length === 0
            text: "At least 12 characters, with upper and lower case letters, a digit and a symbol."
        }
        Notice { width: parent.width; text: settings.message }

        footer: [
            PrimaryButton { quiet: true; text: "Cancel"; onClicked: passwordDialog.close() },
            PrimaryButton {
                text: settings.busy ? "Saving…" : "Change password"
                enabled: !settings.busy
                onClicked: passwordDialog.submit()
            }
        ]
    }

    Sheet {
        id: backupDialog
        objectName: "backupDialog"
        title: "Create a backup"
        subtitle: "Choose a password for this backup file. It is separate from your sign-in password and cannot be recovered."

        function openFresh() {
            phrase.text = ""; phraseAgain.text = ""
            settings.clearMessage()
            open()
            phrase.input.forceActiveFocus()
        }

        Connections {
            target: settings
            function onSaved() { if (backupDialog.visible) backupDialog.close() }
        }

        Field {
            id: phrase
            width: parent.width
            label: "Backup password (at least 12 characters)"
            echoMode: TextInput.Password
            onAccepted: phraseAgain.input.forceActiveFocus()
        }
        Field {
            id: phraseAgain
            width: parent.width
            label: "Repeat backup password"
            echoMode: TextInput.Password
        }
        Notice { width: parent.width; text: settings.message }

        footer: [
            PrimaryButton { quiet: true; text: "Cancel"; onClicked: backupDialog.close() },
            PrimaryButton {
                text: settings.busy ? "Creating…" : "Choose where to save"
                enabled: !settings.busy && phrase.text.length > 0
                onClicked: backupFile.open()
            }
        ]
    }

    FileDialog {
        id: backupFile
        title: "Save backup"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Helysofer backup (*" + settings.backupSuffix + ")"]
        defaultSuffix: settings.backupSuffix.substring(1)
        onAccepted: settings.createBackup(selectedFile, phrase.text, phraseAgain.text)
    }

    FileDialog {
        id: restoreFile
        title: "Choose a backup to restore"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Helysofer backup (*" + settings.backupSuffix + ")", "All files (*)"]
        onAccepted: restorePrompt.openFor({ file: selectedFile.toString() }, "")
    }

    Prompt {
        id: renamePrompt
        objectName: "renamePrompt"
        source: categories
        title: "Rename category"
        subtitle: "Everything filed under it moves to the new name."
        fieldLabel: "Name"
        onSubmitted: function (text) { categories.rename(subject.key, text) }
    }

    Prompt {
        id: restorePrompt
        objectName: "restorePrompt"
        source: settings
        title: "Restore this backup?"
        subtitle: "Everything on this device is replaced, then Helysofer closes so it can start from the restored data."
        fieldLabel: "Backup password"
        secret: true
        danger: true
        confirmText: "Restore"
        onSubmitted: function (text) { settings.restoreBackup(subject.file, text) }
    }

    FileDialog {
        id: exportFile
        title: "Export to CSV"
        fileMode: FileDialog.SaveFile
        nameFilters: ["CSV (*.csv)"]
        defaultSuffix: "csv"
        onAccepted: settings.exportCsv(selectedFile)
    }

    FileDialog {
        id: importFile
        title: "Choose a CSV file"
        fileMode: FileDialog.OpenFile
        nameFilters: ["CSV (*.csv)", "All files (*)"]
        onAccepted: importDialog.openFor(selectedFile.toString())
    }

    Sheet {
        id: importDialog
        objectName: "importDialog"
        property string file: ""
        title: "Import transactions"
        subtitle: "Each row is added as a transaction with its original date and changes the account's balance."

        function openFor(url) {
            file = url
            settings.clearMessage()
            if (accounts.options.length === 1) target.select(accounts.options[0].key)
            else target.select(-1)
            open()
        }

        Connections {
            target: settings
            function onSaved() { if (importDialog.visible) importDialog.close() }
        }

        Choice {
            id: target
            width: parent.width
            label: "Add to account"
            placeholder: "Choose an account"
            model: accounts.options
        }
        Notice { width: parent.width; text: settings.message }

        footer: [
            PrimaryButton { quiet: true; text: "Cancel"; onClicked: importDialog.close() },
            PrimaryButton {
                text: settings.busy ? "Importing…" : "Import"
                enabled: !settings.busy
                onClicked: settings.importCsv(importDialog.file,
                                              target.currentKey === undefined ? -1 : target.currentKey)
            }
        ]
    }

    Prompt {
        id: resetDialog
        objectName: "resetDialog"
        source: settings
        title: "Delete all data?"
        subtitle: "Every account, transaction, debt, recurring payment and your password are erased from this device. This cannot be undone."
        fieldLabel: "Type " + settings.confirmationWord + " to confirm"
        danger: true
        confirmText: "Delete everything"
        onSubmitted: function (text) { settings.resetAll(text) }
    }
}
