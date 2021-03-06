import tensorflow as tf
import os
from record_reader import TextLoader
from model import SRLModel
from inference import recover
import codecs
import cPickle

# Parameters
# ==================================================

# Model Hyperparameters
tf.flags.DEFINE_integer("embedding_dim", 128, "Dimensionality of character embedding (default: 128)")
tf.flags.DEFINE_integer("mark_embedding_dim", 128, "Dimensionality of character embedding (default: 128)")
tf.flags.DEFINE_integer("hidden_size", 128, "Dimensionality of character embedding (default: 128)")

# Training parameters
tf.flags.DEFINE_integer("batch_size", 1115, "Batch Size (default: 64)")
tf.flags.DEFINE_integer("num_gpus", 1, "Batch Size (default: 64)")
tf.flags.DEFINE_integer("num_layers", 4, "Number of training epochs (default: 200)")
tf.flags.DEFINE_string('cell', 'highway', 'checkpoint')
tf.flags.DEFINE_string('train_dir', 'check_attention', 'checkpoint')
tf.flags.DEFINE_string('load_model', 'check_attention', 'checkpoint')


FLAGS = tf.flags.FLAGS


def convert(inputs, labels, is_training):
    if is_training:
        word_vocab_file = os.path.join('data', 'train_id_to_word.pkl')
        with open(word_vocab_file, 'rb') as f:
            word_vocab = cPickle.load(f)
    else:
        word_vocab_file = os.path.join('data', 'valid_id_to_word.pkl')
        with open(word_vocab_file, 'rb') as f:
            word_vocab = cPickle.load(f)

    label_vocab_file = os.path.join('data', 'id_to_label.pkl')
    with open(label_vocab_file, 'rb') as f:
        label_vocab = cPickle.load(f)
    new_inputs = []
    for line, label in zip(inputs, labels):
        new_input = []
        for word_id, label_id in zip(line, label):
            #print word_vocab[word_id] + '/' + label_vocab[label_id]
            new_input.append(word_vocab[word_id] + '/' + label_vocab[label_id])
        new_inputs.append(new_input)
    return new_inputs


def final(preds, writer):
    #preds = [pred.split() for pred in preds.split('\n')]
    #num = 0
    for pred in preds:
     #   num += 1
      #  if num != 6:
       #     continue
        lastname = ''
        keys_pred = {}
        word_to_label = {}
        for id, item in enumerate(pred):
            word, label = item.split('/')[0], item.split('/')[-1]
            word_to_label[str(id)] = label
            flag, name = label[:label.find('-')], label[label.find('-') + 1:]
            if flag == 'O':
                continue
            if flag == 'S':
                if name not in keys_pred:
                    keys_pred[name] = [str(id)]
                else:
                    keys_pred[name].append(str(id))
            else:
                if flag == 'B':
                    if name not in keys_pred:
                        keys_pred[name] = [str(id)]
                    else:
                        keys_pred[name].append(str(id))
                    lastname = name
                elif flag == 'I':
                    assert name == lastname, "the I-/E- labels are inconsistent with B- labels in pred file."
                    keys_pred[name][-1] += ' ' + str(id)
        for key in keys_pred.keys():
            value = keys_pred[key]
            for val in value:
                val_list = val.split()
                if len(val_list) == 1:
                    word_to_label[str(val_list[0])] = 'S-' + key
                if len(val_list) > 1:
                    word_to_label[str(val_list[-1])] = 'E-' + key
        content = []
        for id, item in enumerate(pred):
            word, label = item.split('/')[0], item.split('/')[-1]
            content.append(word + '/' + word_to_label[str(id)])
        writer.write(' '.join(content) + '\n')


def main(_):

    valid_loader = TextLoader('valid', FLAGS.batch_size, 1, 1, 1)
    batch_queue_data = valid_loader.batch_data
    print("Loading data...")
    # Training
    # ==================================================

    with tf.variable_scope('SRLModel'):
        valid_cnn = SRLModel(
            batch_queue_data[0],
            batch_queue_data[1],
            batch_queue_data[2],
            batch_queue_data[3],
            labels=batch_queue_data[4],
            ori_inputs=batch_queue_data[-1],
            seq_length=batch_queue_data[5],
            num_classes=36,
            vocab_size=381057,
            embedding_size=FLAGS.embedding_dim,
            mark_embedding_size=FLAGS.mark_embedding_dim,
            batch_size=FLAGS.batch_size,
            cell_name=FLAGS.cell,
            hidden_size=FLAGS.hidden_size,
            num_layers=FLAGS.num_layers,
            dropout_keep_proba=1.0,
            dropout_mode=False,
            is_training=False
        )

        session_conf = tf.ConfigProto(
            allow_soft_placement=True,
            log_device_placement=True)
        sess = tf.Session(config=session_conf)

        sess.run(tf.local_variables_initializer())
        sess.run(tf.global_variables_initializer())
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(sess=sess, coord=coord)

        saver = tf.train.Saver()
        num_batches_valid = int(1115 / FLAGS.batch_size)
        check_point = os.path.join(FLAGS.train_dir, FLAGS.load_model)
        saver.restore(sess, check_point)
        global_step = check_point.split('/')[-1].split('-')[-1]
        global_step = int(global_step)

        for step in range(num_batches_valid):
            inputs, scores, golds, lens, batch_loss = sess.run([
                valid_cnn.ori_inputs,
                valid_cnn.scores,
                valid_cnn.labels,
                valid_cnn.seq_length,
                valid_cnn.loss])

            inputs, preds, golds = recover(inputs, scores, golds, lens)
            preds = convert(inputs, preds, False)
            golds = convert(inputs, golds, False)
            with codecs.open('data/cpbdev.txt', 'rb', encoding='utf-8') as f:
                with codecs.open('cpbdev1.txt', 'wb', encoding='utf-8') as writer:
                    for line in f:
                        line = line.strip()
                        line = line.split()
                        if not len(line):
                            continue
                        content = []
                        for labeled_word in line:
                            labeled_word = labeled_word.split('/')
                            content.append(labeled_word[0] + '/' + labeled_word[2])
                        writer.write(' '.join(content) + '\n')

            with codecs.open('cpbdev2.txt', 'wb', encoding='utf-8') as writer:
                for gold in golds:
                    writer.write(' '.join(gold) + '\n')
            with codecs.open('cpbdev_answer2.txt', 'wb', encoding='utf-8') as writer:
                for pred in preds:
                    writer.write(' '.join(pred) + '\n')
            writer = codecs.open('cpbdev_answer1.txt', 'wb', encoding='utf-8')
            final(preds, writer)


if __name__ == "__main__":
    tf.app.run()
    #with codecs.open('cpbdev_answer.txt', 'rb', encoding='utf-8') as f:
     #   writer = codecs.open('cpbdev_answer1.txt', 'wb', encoding='utf-8')
      #  final(f.read().strip(), writer)
