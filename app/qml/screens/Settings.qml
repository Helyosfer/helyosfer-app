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
                text: qsTr("Settings")
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
                heading: qsTr("Appearance")
                SettingRow {
                    title: qsTr("Dark theme")
                    detail: qsTr("Applies immediately and is remembered on this device.")
                    Toggle {
                        checked: app.dark
                        onToggled: app.toggleTheme()
                    }
                }
                SettingRow {
                    title: qsTr("Animations")
                    detail: qsTr("Turn off to make every change immediate.")
                    Toggle {
                        objectName: "motionToggle"
                        checked: app.motion
                        onToggled: app.setMotion(checked)
                    }
                }
                SettingRow {
                    title: qsTr("Language")
                    detail: qsTr("Amounts and dates are written the same way in both.")
                    Segmented {
                        objectName: "languageChoice"
                        model: app.languages
                        current: app.language
                        onChosen: function (key) { app.setLanguage(key) }
                    }
                }
            }

            Section {
                heading: qsTr("Security")
                SettingRow {
                    title: qsTr("Password")
                    detail: qsTr("You will be asked to sign in again after changing it.")
                    PrimaryButton {
                        compact: true; quiet: true
                        text: qsTr("Change password")
                        onClicked: passwordDialog.openFresh()
                    }
                }
                SettingRow {
                    title: qsTr("Encryption key")
                    detail: settings.keyWarning.length > 0
                        ? settings.keyProtection + " — " + settings.keyWarning
                        : qsTr("Protected by %1.").arg(settings.keyProtection)
                    warning: settings.keyWarning.length > 0
                }
            }

            Section {
                heading: qsTr("Backup")
                SettingRow {
                    title: qsTr("Create a backup")
                    detail: qsTr("One encrypted file with your records, the encryption key and your settings. It is protected by a separate backup password.")
                    PrimaryButton {
                        compact: true; quiet: true
                        text: qsTr("Create backup")
                        onClicked: backupDialog.openFresh()
                    }
                }
                SettingRow {
                    title: qsTr("Restore from a backup")
                    detail: qsTr("Replaces everything on this device with the backup's contents. A safety copy of the current state is kept next to your data.")
                    PrimaryButton {
                        compact: true; quiet: true
                        text: qsTr("Restore")
                        enabled: !settings.busy
                        onClicked: restoreFile.open()
                    }
                }
            }

            Section {
                heading: qsTr("Import and export")
                SettingRow {
                    title: qsTr("Export to CSV")
                    detail: qsTr("Transactions, assets, debts and recurring payments in one spreadsheet file. The file is not encrypted.")
                    PrimaryButton {
                        compact: true; quiet: true
                        text: qsTr("Export")
                        enabled: !settings.busy
                        onClicked: exportFile.open()
                    }
                }
                SettingRow {
                    title: qsTr("Import transactions from CSV")
                    detail: qsTr("Adds the transactions in a CSV file to one of your accounts. Rows that cannot be read are skipped.")
                    PrimaryButton {
                        compact: true; quiet: true
                        text: qsTr("Import")
                        enabled: !settings.busy
                        onClicked: importFile.open()
                    }
                }
            }

            Section {
                id: categorySection
                heading: qsTr("Categories")
                property string kind: "expense"

                Component.onCompleted: categories.refresh()

                Item {
                    width: parent.width
                    height: kindChoice.height + 12

                    Text {
                        anchors.verticalCenter: kindChoice.verticalCenter
                        width: parent.width - kindChoice.width - 24
                        text: qsTr("Essential categories are counted as needs in summaries and the health score; the rest as extras.")
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Segmented {
                        id: kindChoice
                        anchors.right: parent.right
                        model: [{ key: "expense", label: qsTr("Spending") }, { key: "income", label: qsTr("Income") }]
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
                            visible: categoryRow.modelData.editable

                            PrimaryButton {
                                quiet: true
                                compact: true
                                text: qsTr("Rename")
                                onClicked: renamePrompt.openFor(categoryRow.modelData, categoryRow.modelData.name)
                            }
                            PrimaryButton {
                                quiet: true
                                danger: true
                                compact: true
                                text: qsTr("Remove")
                                enabled: !categories.busy
                                onClicked: {
                                    if (categoryRow.modelData.inUse) moveDialog.openFor(categoryRow.modelData)
                                    else categories.remove(categoryRow.modelData.key)
                                }
                            }
                        }
                        Toggle {
                            id: essential
                            anchors.right: parent.right
                            anchors.rightMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: qsTr("Essential")
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
                            label: categorySection.kind === "income" ? qsTr("New income category") : qsTr("New spending category")
                            placeholder: qsTr("Name")
                            onAccepted: categories.add(categorySection.kind, text, newEssential.checked)
                        }
                        Item {
                            width: newEssential.width
                            height: newCategory.height
                            Toggle {
                                id: newEssential
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 10
                                text: qsTr("Essential")
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
                                text: qsTr("Add category")
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
                heading: qsTr("Danger zone")
                SettingRow {
                    title: qsTr("Delete all data")
                    detail: qsTr("Erases every account, transaction, debt and setting, and your password. This cannot be undone; create a backup first.")
                    PrimaryButton {
                        compact: true; quiet: true; danger: true
                        text: qsTr("Delete everything")
                        onClicked: resetDialog.openFor(null, "")
                    }
                }
            }

            Section {
                heading: qsTr("About")
                SettingRow {
                    title: "Helyosfer " + app.version
                    detail: qsTr("Questions, feedback and bug reports: %1").arg(settings.projectUrl)
                        + "  ·  " + settings.contactEmail
                }
                SettingRow {
                    title: qsTr("Where your data is kept")
                    detail: settings.dataFolder
                }
            }
        }
    }

    // -- Dialogs --------------------------------------------------------------
    Sheet {
        id: passwordDialog
        objectName: "passwordDialog"
        title: qsTr("Change password")

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
            label: qsTr("Current password")
            echoMode: TextInput.Password
            onAccepted: next.input.forceActiveFocus()
        }
        Field {
            id: next
            width: parent.width
            label: qsTr("New password")
            echoMode: TextInput.Password
            onAccepted: again.input.forceActiveFocus()
        }
        Field {
            id: again
            width: parent.width
            label: qsTr("Repeat new password")
            echoMode: TextInput.Password
            onAccepted: passwordDialog.submit()
        }
        Notice {
            width: parent.width
            problem: false
            visible: settings.message.length === 0
            text: qsTr("At least 12 characters, with upper and lower case letters, a digit and a symbol.")
        }
        Notice { width: parent.width; text: settings.message }

        footer: [
            PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: passwordDialog.close() },
            PrimaryButton {
                text: settings.busy ? qsTr("Saving…") : qsTr("Change password")
                enabled: !settings.busy
                onClicked: passwordDialog.submit()
            }
        ]
    }

    Sheet {
        id: backupDialog
        objectName: "backupDialog"
        title: qsTr("Create a backup")
        subtitle: qsTr("Choose a password for this backup file. It is separate from your sign-in password and cannot be recovered.")

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
            label: qsTr("Backup password (at least 12 characters)")
            echoMode: TextInput.Password
            onAccepted: phraseAgain.input.forceActiveFocus()
        }
        Field {
            id: phraseAgain
            width: parent.width
            label: qsTr("Repeat backup password")
            echoMode: TextInput.Password
        }
        Notice { width: parent.width; text: settings.message }

        footer: [
            PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: backupDialog.close() },
            PrimaryButton {
                text: settings.busy ? qsTr("Creating…") : qsTr("Choose where to save")
                enabled: !settings.busy && phrase.text.length > 0
                onClicked: backupFile.open()
            }
        ]
    }

    FileDialog {
        id: backupFile
        title: qsTr("Save backup")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Helyosfer backup") + " (*" + settings.backupSuffix + ")"]
        defaultSuffix: settings.backupSuffix.substring(1)
        onAccepted: settings.createBackup(selectedFile, phrase.text, phraseAgain.text)
    }

    FileDialog {
        id: restoreFile
        title: qsTr("Choose a backup to restore")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Helyosfer backup") + " (*" + settings.backupSuffix + ")", qsTr("All files") + " (*)"]
        onAccepted: restorePrompt.openFor({ file: selectedFile.toString() }, "")
    }

    Sheet {
        id: moveDialog
        objectName: "moveDialog"
        property var subject: null
        title: subject ? qsTr("Remove %1?").arg(subject.name) : ""
        subtitle: qsTr("Transactions, plan items and recurring payments are filed under it. Choose the category that takes them over.")

        function openFor(item) {
            subject = item
            categories.clearMessage()
            successor.select("")
            open()
        }

        Connections {
            target: categories
            function onSaved() { if (moveDialog.visible) moveDialog.close() }
        }

        Choice {
            id: successor
            width: parent.width
            label: qsTr("Move its records to")
            placeholder: qsTr("Choose a category")
            model: moveDialog.subject
                ? (transactions.categoryRevision, transactions.categories(moveDialog.subject.kind)).filter(
                      function (option) { return option.key !== moveDialog.subject.key })
                : []
        }
        Notice { width: parent.width; text: categories.message }

        footer: [
            PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: moveDialog.close() },
            PrimaryButton {
                quiet: true
                danger: true
                text: categories.busy ? qsTr("Working…") : qsTr("Move and remove")
                enabled: !categories.busy
                onClicked: categories.removeAndMove(
                    moveDialog.subject.key,
                    successor.currentKey === undefined ? "" : successor.currentKey)
            }
        ]
    }

    Prompt {
        id: renamePrompt
        objectName: "renamePrompt"
        source: categories
        title: qsTr("Rename category")
        subtitle: qsTr("Everything filed under it moves to the new name.")
        fieldLabel: qsTr("Name")
        onSubmitted: function (text) { categories.rename(subject.key, text) }
    }

    Prompt {
        id: restorePrompt
        objectName: "restorePrompt"
        source: settings
        title: qsTr("Restore this backup?")
        subtitle: qsTr("Everything on this device is replaced, then Helyosfer closes so it can start from the restored data.")
        fieldLabel: qsTr("Backup password")
        secret: true
        danger: true
        confirmText: qsTr("Restore")
        onSubmitted: function (text) { settings.restoreBackup(subject.file, text) }
    }

    FileDialog {
        id: exportFile
        title: qsTr("Export to CSV")
        fileMode: FileDialog.SaveFile
        nameFilters: ["CSV (*.csv)"]
        defaultSuffix: "csv"
        onAccepted: settings.exportCsv(selectedFile)
    }

    FileDialog {
        id: importFile
        title: qsTr("Choose a CSV file")
        fileMode: FileDialog.OpenFile
        nameFilters: ["CSV (*.csv)", qsTr("All files") + " (*)"]
        onAccepted: importDialog.openFor(selectedFile.toString())
    }

    Sheet {
        id: importDialog
        objectName: "importDialog"
        property string file: ""
        title: qsTr("Import transactions")
        subtitle: qsTr("Each row is added as a transaction with its original date and changes the account's balance.")

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
            label: qsTr("Add to account")
            placeholder: qsTr("Choose an account")
            model: accounts.options
        }
        Notice { width: parent.width; text: settings.message }

        footer: [
            PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: importDialog.close() },
            PrimaryButton {
                text: settings.busy ? qsTr("Importing…") : qsTr("Import")
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
        title: qsTr("Delete all data?")
        subtitle: qsTr("Every account, transaction, debt, recurring payment and your password are erased from this device. This cannot be undone.")
        fieldLabel: qsTr("Type %1 to confirm").arg(settings.confirmationWord)
        danger: true
        confirmText: qsTr("Delete everything")
        onSubmitted: function (text) { settings.resetAll(text) }
    }
}
